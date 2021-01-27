"""Application configuration."""
import os
from pathlib import Path
from aenum import Constant
from dotenv import load_dotenv

env_path = os.path.join(Path(__file__).parent.absolute(), 'awstools.env')
load_dotenv(dotenv_path=env_path)


class Env(Constant):
    """Base configuration."""
    # Environment
    ENV = os.environ.get('ENV', 'stg').lower()
    APP_NAME = os.environ.get('APP_NAME').lower()
    assert os.environ.get('DEBUG') in ['True', 'False']
    DEBUG = os.environ.get('DEBUG') == 'True'

    # Unmatched tweets
    UNMATCHED_STORE_LOCALLY = os.environ.get(
        'UNMATCHED_STORE_LOCALLY', 'False')
    assert UNMATCHED_STORE_LOCALLY in ['True', 'False']
    UNMATCHED_STORE_LOCALLY = int(UNMATCHED_STORE_LOCALLY == 'True')

    UNMATCHED_STORE_S3 = os.environ.get(
        'UNMATCHED_STORE_S3', 'False')
    assert UNMATCHED_STORE_S3 in ['True', 'False']
    UNMATCHED_STORE_S3 = int(UNMATCHED_STORE_S3 == 'True')

    # Paths
    APP_DIR = os.path.abspath(os.path.dirname(__file__))  # This directory
    PROJECT_ROOT = os.path.abspath(os.path.join(APP_DIR, os.pardir))
    CONFIG_PATH = os.path.abspath(os.path.join(APP_DIR, 'config'))

    # Other
    TIMEZONE = os.environ.get('TIMEZONE', 'Europe/Zurich')
    S3_BUCKET_PREFIX = os.environ.get('S3_BUCKET_PREFIX', 'project_')


class AWSEnv(Env):
    """AWS config (for storing in S3, accessing Elasticsearch)."""
    REGION = os.environ.get('AWS_REGION', 'eu-central-1')
    ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    ACCOUNT_NUM = os.environ.get('AWS_ACCOUNT_NUM')
    BUCKET_NAME = os.environ.get(
        'AWS_BUCKET_NAME', Env.APP_NAME + '-' + Env.ENV)
    CONFIG_S3_KEY = os.environ.get(
        'CONFIG_S3_KEY', 'configs/stream/stream.json')
    ENDPOINTS_PREFIX = os.environ.get(
        'ENDPOINTS_PREFIX', 'configs/models/')


class KFEnv(AWSEnv):
    BUCKET_FOLDER = os.environ.get('AWS_KF_BUCKET_FOLDER', 'tweets/')
    BUCKET_PREFIX = os.environ.get('AWS_KF_BUCKET_PREFIX', 'project_')
    ROLE_TRUST_RELATIONSHIP_PATH = os.path.join(
        AWSEnv.CONFIG_PATH,
        os.environ.get('AWS_KF_ROLE_TRUST_RELATIONSHIP_FILENAME'))
    POLICY_PATH = os.path.join(
        AWSEnv.CONFIG_PATH,
        os.environ.get('AWS_KF_POLICY_FILENAME'))
    BUFFER_SIZE = int(os.environ.get('AWS_KF_BUFFER_SIZE', '50'))
    BUFFER_INTERVAL = int(os.environ.get('AWS_KF_BUFFER_INTERVAL', '60'))
    UNMATCHED_STREAM_NAME = os.environ.get(
        'AWS_KF_UNMATCHED_STREAM_NAME', 'unmatched')


class LEnv(AWSEnv):
    BUCKET_FOLDER = os.environ.get('AWS_KF_BUCKET_FOLDER', 'tweets/')
    BUCKET_PREFIX = os.environ.get('AWS_KF_BUCKET_PREFIX', 'project_')
    ROLE_TRUST_RELATIONSHIP_PATH = os.path.join(
        AWSEnv.CONFIG_PATH,
        os.environ.get('AWS_L_ROLE_TRUST_RELATIONSHIP_FILENAME'))
    POLICY_PATH = os.path.join(
        AWSEnv.CONFIG_PATH,
        os.environ.get('AWS_L_POLICY_FILENAME'))
    HANDLER = os.environ.get(
        'AWS_L_HANDLER', 's3_preprocess_to_es.handler')
    DESCRIPTION = os.environ.get(
        'AWS_L_DESCRIPTION',
        'Take new tweets from S3, preprocess and put to ES.')
    TIMEOUT = int(os.environ.get('AWS_L_TIMEOUT', '300'))
    MEMORY_SIZE = int(os.environ.get('AWS_L_MEMORY_SIZE', '128'))
    PATH_TO_FUNC = os.environ.get('AWS_L_PATH_TO_FUNC', 'lambda/lambda')
    PATH_TO_LAYER = os.environ.get('AWS_L_PATH_TO_LAYER', 'lambda/layer')
    PATH_TO_FUNC_DIR = os.environ.get(
        'AWS_L_PATH_TO_FUNC_DIR', 'lambda/function')
    PATH_TO_LAYER_DIR = os.environ.get(
        'AWS_L_PATH_TO_LAYER_DIR', 'lambda/layer')
    EXTENSION = os.environ.get('AWS_L_EXTENSION', 'zip')


class ESEnv(AWSEnv):
    HOST = os.environ.get('ES_HOST', '')
    PORT = os.environ.get('ES_PORT', -1)
    INDEX_PREFIX = os.environ.get('ES_INDEX_PREFIX', 'project_')
    DOMAIN = os.environ.get(
        'AWS_ES_DOMAIN', Env.APP_NAME + '-' + Env.ENV + '-es')


class SMEnv(AWSEnv):
    BATCH_SIZE_DEFAULT = int(os.environ.get('BATCH_SIZE_DEFAULT', '1'))
    BATCH_SIZE_FASTTEXT = int(os.environ.get('BATCH_SIZE_FASTTEXT', '100'))
