import logging
import json
# import re
import os
from copy import deepcopy

from elasticsearch import ConflictError, ElasticsearchException, RequestError
# from elasticsearch.helpers import bulk
from geocode.geocode import Geocode

import twiprocess as twp
from twiprocess.processtweet import ProcessTweet
from awstools.env import ESEnv, SMEnv
from awstools.config import config_manager
from awstools.session import session, es, s3
from awstools.s3 import get_long_s3_object

DEFAULT_STANDARDIZE_FUNC_NAME = 'standardize_anonymize'

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

geo_code = Geocode()
geo_code.load()

credentials = session.get_credentials()
sagemaker = session.client('sagemaker-runtime')


# def preprocess(status):
#     status = status.replace('\n', ' ')
#     status = re.sub(' +', ' ', status).strip()
#     return status


def get_batch_size(model_type):
    if model_type == 'fasttext':
        return SMEnv.BATCH_SIZE_FASTTEXT
    logger.warning(
        'Model type %s unknown. Using default batch size.', model_type)
    return SMEnv.BATCH_SIZE_DEFAULT


def labels_to_int(labels):
    """Heuristic to convert label to numeric value.
    Parses leading numbers in label tags such as 1_worried -> 1.
    If any conversion fails, returns None.
    """
    label_vals = []
    for label in labels:
        if label == 'positive':
            label_vals.append(1)
        elif label == 'negative':
            label_vals.append(-1)
        elif label == 'neutral':
            label_vals.append(0)
        else:
            label_split = label.split('_')
            try:
                label_val = int(label_split[0])
            except ValueError:
                return
            label_vals.append(label_val)
    return label_vals


def preprocess(preprocessing_config, texts):
    # Preprocess data
    try:
        standardize_func_name = preprocessing_config['standardize_func_name']
        del preprocessing_config['standardize_func_name']
    except KeyError:
        standardize_func_name = DEFAULT_STANDARDIZE_FUNC_NAME
    if standardize_func_name is not None:
        logger.debug('Standardizing data...')
        standardize_func = getattr(
            __import__(
                'twiprocess.standardize',
                fromlist=[standardize_func_name]),
            standardize_func_name)
        texts = [standardize_func(text) for text in texts]
    if preprocessing_config != {}:
        logger.debug('Preprocessing data...')
        texts = [
            twp.preprocess(text, **preprocessing_config) for text in texts]
    return texts


def predict(endpoint_name, preprocessing_config, texts, batch_size):
    """Runs prediction in batches."""
    outputs = []
    for i in range(0, len(texts), batch_size):
        logger.debug('Batch %d', i)
        batch = preprocess(preprocessing_config, texts[i:i + batch_size])
        logger.debug('Batch:\n%s', batch)

        try:
            response = sagemaker.invoke_endpoint(
                EndpointName=endpoint_name,
                Body=json.dumps({'text': batch}),
                ContentType='application/json'
            )
        except sagemaker.exceptions.ModelError as exc:
            logger.error('%s: %s', type(exc).__name__, str(exc))
            outputs.extend([None] * batch_size)
        finally:
            predictions = json.loads(
                response['Body'].read().decode('utf-8')
            )['predictions']
            outputs.extend([{
                'labels': pred['labels'],
                'probabilities': pred['probabilities']
            } for pred in predictions])

    label_valss = [labels_to_int(output['labels']) for output in outputs]
    if all(label_valss):
        outputs = [{
            'label_vals': label_vals, **output
        } for output, label_vals in zip(outputs, label_valss)]

    return outputs


def handler(event, context):
    logger.debug(event)
    for record in event['Records']:
        # Get bucket name and key for new file
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        # Get slug
        slug = [
            name for name in key.split('/')
            if name.startswith(ESEnv.INDEX_PREFIX)
        ]
        if len(slug) != 1:
            logger.error('Slug len != 1.\nKey: %s.\nSlug: %s.', key, slug)
        slug = slug[0][len(ESEnv.INDEX_PREFIX):]
        logger.debug('Slug: %s.', slug)

        # Get model endpoints from config
        model_endpoints = config_manager.get_conf_by_slug(slug).model_endpoints

        # Get S3 object
        records = get_long_s3_object(
            bucket, key,
            {'CompressionType': 'GZIP', 'JSON': {'Type': 'LINES'}})

        try:
            statuses = [json.loads(record) for record in records.splitlines()]
        except json.JSONDecodeError as exc:
            logger.error('%s: %s', type(exc).__name__, str(exc))
            logger.error('Rec:\n%s', str(record))
            continue

        logger.debug('Num records: %s.', len(statuses))

        texts = [status['text'] for status in statuses]

        # Read off stream config and prepare a template for metadata
        prediction = {}
        endpoint_names = {}
        run_names = {}
        model_types = {}
        preprocessing_configs = {}
        for question_tag in model_endpoints:
            endpoint_names[question_tag] = []
            run_names[question_tag] = []
            model_types[question_tag] = []
            prediction[question_tag] = {'endpoints': {}}
            preprocessing_configs[question_tag] = []
            for endpoint_name, info in \
                    model_endpoints[question_tag]['active'].items():
                endpoint_names[question_tag].append(endpoint_name)
                run_names[question_tag].append(info['run_name'])
                model_types[question_tag].append(info['model_type'])

                key = os.path.join(
                    ESEnv.ENDPOINTS_PREFIX, endpoint_name + '.json')
                logger.debug(f'Key: {key}')

                try:
                    logger.debug('Trying to load from S3')
                    run_config = json.loads(get_long_s3_object(
                        ESEnv.BUCKET_NAME, key,
                        {'CompressionType': 'NONE', 'JSON':
                            {'Type': 'DOCUMENT'}}))
                except Exception:
                    logger.debug('Some error, addind an empty config')
                    run_config = {'preprocess': {}}

                preprocessing_configs[question_tag].append(
                    run_config['preprocess'])

        predictions = [deepcopy(prediction)] * len(texts)
        logger.info('Endpoint names:\n%s.', endpoint_names)

        def predictions_from_output(output, primary=False):
            max_prob = max(output['probabilities'])
            ind_max_prob = output['probabilities'].index(max_prob)
            prefix = 'primary_' if primary else ''
            return {
                f'{prefix}probability': max_prob,
                f'{prefix}label': output['labels'][ind_max_prob],
                f'{prefix}label_val': output['label_vals'][ind_max_prob]
            }

        # Fill metadata with predictions
        for question_tag in endpoint_names:
            primary_endpoint_name = model_endpoints[question_tag]['primary']
            for (
                endpoint_name,
                model_type,
                run_name,
                preprocessing_config
            ) in zip(
                endpoint_names[question_tag],
                model_types[question_tag],
                run_names[question_tag],
                preprocessing_configs[question_tag]
            ):
                batch_size = get_batch_size(model_type)

                outputs = predict(
                    endpoint_name, preprocessing_config, texts, batch_size)

                if outputs is None:
                    continue

                if endpoint_name == primary_endpoint_name:
                    for i, output in enumerate(outputs):
                        predictions[i][question_tag]['endpoints'] = \
                            predictions_from_output(output, primary=True)

                for i, output in enumerate(outputs):
                    predictions[i][question_tag]['endpoints'][run_name] = \
                        predictions_from_output(output)

        # Process tweets for ES
        statuses_es = []
        for status in statuses:
            statuses_es.append(ProcessTweet(
                status, standardize_func='standardize', geo_code=geo_code
            ).extract_es(extract_geo=True))

        # Add 'predictions' field to statuses
        for i in range(len(statuses)):
            # This way, if prediction fails, we at least store the tweet
            if predictions[i] != prediction:
                # Keep the failed predictions empty
                statuses_es[i]['predictions'] = predictions[i]

        logger.debug('\n\n'.join([json.dumps(status) for status in statuses]))

        # Load to Elasticsearch
        # index_name = \
        #     ESEnv.INDEX_PREFIX + slug
        indices = json.loads(get_long_s3_object(
            ESEnv.BUCKET_NAME, ESEnv.CONFIG_S3_KEY,
            {'CompressionType': 'NONE', 'JSON': {'Type': 'DOCUMENT'}}))
        index_name = indices[slug][-1]
        logger.debug(index_name)

        def create_doc(status_id, status_es, loads, errors, request_errors):
            try:
                es.create(
                    index=index_name, id=status_id,
                    body=json.dumps(status_es), doc_type='_doc')
                logger.debug('Loaded rec %d, id %s.', i, status_id)
                loads += 1
            except ConflictError as exc:
                # Happens when a document with the same ID
                # already exists.
                errors += 1
                logger.warning(
                    'Rec %d, id %s already exists.', i, status_id)
                # logger.error('%s: %s', type(exc).__name__, str(exc))
            except RequestError as exc:
                errors += 1
                request_errors += 1
                if request_errors < 5:
                    logger.error(json.dumps(status_es))
                    logger.error(type(status_es['geo_info']['country_code']))
                    logger.error(
                        '%s: %s. Retrying...', type(exc).__name__, str(exc))
                    _ = create_doc(
                        status_id, status_es, loads, errors, request_errors)
                else:
                    request_errors = 0
            except ElasticsearchException as exc:
                errors += 1
                logger.error('%s: %s', type(exc).__name__, str(exc))
            return loads, errors

        loads = 0
        errors = 0
        request_errors = 0

        for i, status_es in enumerate(statuses_es):
            logger.debug(status_es)
            status_id = status_es.pop('id')
            loads, errors = create_doc(
                status_id, status_es, loads, errors, request_errors)

        logger.info(
            'Loaded %d/%d to Elasticsearch, already exist %d/%d.',
            loads, len(statuses_es), errors, len(statuses_es))
