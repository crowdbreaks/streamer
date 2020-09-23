import logging
import json

import boto3
from botocore.exceptions import ClientError
from requests_aws4auth import AWS4Auth
from elasticsearch import Elasticsearch, RequestsHttpConnection, ConflictError
# from elasticsearch.helpers import bulk

from env import ESEnv

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(
    credentials.access_key, credentials.secret_key,
    ESEnv.REGION, "es",
    session_token=credentials.token
)

es = Elasticsearch(
    hosts=[{'host': ESEnv.HOST, 'port': ESEnv.PORT}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)

s3 = boto3.client(
    's3',
    region_name=ESEnv.REGION,
    aws_access_key_id=credentials.access_key,
    aws_secret_access_key=credentials.secret_key,
    aws_session_token=credentials.token
)


def preprocess(status):
    return status


def handler(event, context):
    for record in event['Records']:
        # Get bucket name and key for new file
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        # Get S3 object
        records = ''
        repeat = True
        while repeat:
            try:
                response = s3.select_object_content(
                    Bucket=bucket,
                    Key=key,
                    ExpressionType='SQL',
                    Expression="select * from s3object",
                    InputSerialization={
                        'CompressionType': 'GZIP', 'JSON': {'Type': 'LINES'}},
                    OutputSerialization={'JSON': {}}
                )
            except ClientError as exc:
                if exc.response['Error']['Code'] == 'NoSuchKey':
                    logger.error(
                        '%s: %s Key: %s',
                        exc.response['Error']['Code'],
                        exc.response['Error']['Message'],
                        key)
                    continue
                else:
                    raise exc

            for event in response['Payload']:
                # logger.error('Event:\n' + str(event))
                if 'End' in event:
                    repeat = False
                if 'Records' in event:
                    records += event['Records']['Payload'].decode('utf-8')

        # bulk_data = []
        recs = records.splitlines()
        logger.debug('Num records: %s.', len(recs))
        for i, rec in enumerate(recs):
            try:
                status = json.loads(rec)
            except json.JSONDecodeError as exc:
                logger.error('%s: %s', type(exc).__name__, str(exc))
                logger.error('Rec:\n%s', str(rec))
                continue

            index_name = \
                ESEnv.INDEX_PREFIX + status['_tracking_info']['slug']

            try:
                es.create(
                    index=index_name, id=status['id'],
                    body=status, doc_type='tweet')
                logger.debug('Loaded rec %d, id %d.', i, status['id'])
            except ConflictError as exc:
                # Happens when a document with the same ID
                # already exists.
                logger.debug('Rec %d, id %d already exists.', i, status['id'])
                logger.error('%s: %s', type(exc).__name__, str(exc))

        # Does not raise ConflictError, just loads new vesrions
        # of the same doc, if a duplicate.
        #     bulk_doc = {
        #         '_index': index_name,
        #         '_type': 'tweet',
        #         '_id': status['id'],
        #         '_source': status
        #     }
        #     bulk_data.append(bulk_doc)

        # success, _ = bulk(es, bulk_data)
        # logger.info('ElasticSearch indexed %d documents.', success)
