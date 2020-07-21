import os
import sys
import time
import random
import logging
import argparse
import warnings
warnings.filterwarnings("ignore", "Your application has authenticated using end user credentials")
from datetime import datetime, timedelta

import yaml

from google.oauth2 import service_account
from google.cloud import bigquery, storage
from google.cloud.exceptions import NotFound
from googleapiclient import discovery

from mymodel.model import MyModel
import mymodel.parameters as parameters

logger = logging.getLogger(__name__)


def is_success(ml_engine_service, project_id, job_id):
    # State
    wait = 60  # seconds
    timeout_preparing = timedelta(seconds=900)
    timeout_running = timedelta(hours=10)
    api_call_time = datetime.utcnow()
    api_job_name = "projects/{project_id}/jobs/{job_name}".format(project_id=project_id, job_name=job_id)
    job_description = ml_engine_service.projects().jobs().get(name=api_job_name).execute()
    while not job_description["state"] in ["SUCCEEDED", "FAILED", "CANCELLED"]:
        # check here the PREPARING and RUNNING state to detect the abnormalities of ML Engine service
        if job_description["state"] == "PREPARING":
            delta = datetime.utcnow() - api_call_time
            if delta > timeout_preparing:
                logger.error("[ML] PREPARING stage timeout after %ss --> CANCEL job '%s'", delta.seconds, job_id)
                ml_engine_service.projects().jobs().cancel(name=api_job_name, body={}).execute()
                raise Exception
        if job_description["state"] == "RUNNING":
            delta = datetime.utcnow() - api_call_time
            if delta > timeout_running + timeout_preparing:
                logger.error("[ML] RUNNING stage timeout after %ss --> CANCEL job '%s'", delta.seconds, job_id)
                ml_engine_service.projects().jobs().cancel(name=api_job_name, body={}).execute()
                raise Exception

        logger.info("[ML] NEXT UPDATE for job '%s' IN %ss (%ss ELAPSED IN %s STAGE)", job_id, wait, delta.seconds, job_description["state"])
        job_description = ml_engine_service.projects().jobs().get(name=api_job_name).execute()
        time.sleep(wait)
    logger.info("Job '%s' done", job_id)
    # Check the job state
    if job_description["state"] == "SUCCEEDED":
        logger.info("Job '%s' succeeded!", job_id)
        return True
    logger.error(job_description["errorMessage"])
    return False


if __name__ == '__main__':

    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    logging.getLogger('googleapiclient').setLevel(logging.WARNING)
    logging.getLogger('google_auth_httplib2').setLevel(logging.WARNING)
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(description="TEMPLATE", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--account_id", dest="account_id", help="account id to work on")
    parser.add_argument("--task", dest="task", choices=['preprocess', 'check_model', 'train', 'verify_model', 'predict'], help="task to perform")
    parser.add_argument("--env", dest="env", default="local", choices=['local', 'cloud'], help="environment")
    parser.add_argument("--conf", dest="conf", default="conf/template.yaml", help="absolute or relative path to configuration file")

    if len(sys.argv) < 7:
        parser.print_help()
        sys.exit(1)
    args = parser.parse_args()

    ENV = args.env

    root_logger = logging.getLogger()
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.setLevel(logging.DEBUG) # INFO
    root_logger.addHandler(console_handler)

    account_id = args.account_id

    with open(args.conf, 'r') as f:
        config = yaml.safe_load(f)

    # DEFINE GS AND BQ CLIENT
    project = config['google_cloud']['project']
    if config['google_cloud']['credentials_json_file'] != "":
        credentials = service_account.Credentials.from_service_account_file(config['google_cloud']['credentials_json_file'])
        gs_client = storage.Client(project=project, credentials=credentials)
        bq_client = bigquery.Client(project=project, credentials=credentials)
    else:
        credentials = None
        gs_client = storage.Client(project=project)
        bq_client = bigquery.Client(project=project)

    # DEFINE DATASET REF
    dataset_ref = bq_client.dataset('template')
    try:
        bq_client.get_dataset(dataset_ref)
    except NotFound as nf:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "EU"
        #  bq_client.create_dataset(dataset)
        logger.info("Dataset %s created.", dataset)

    # DEFINE BUCKET
    bucket_id = config['google_cloud']['bucket_id']
    bucket = gs_client.bucket(bucket_id)

    dir_path = os.path.dirname(os.path.abspath(__file__))

    if ENV == 'cloud':
        logger.info('Checking if packages needed by ML engine are available')
        packages = {p: 'gs://{bucket}/template/packages/{package}'.format(
            bucket=bucket.name, package=p) for p in os.listdir(os.path.join(dir_path, 'packages'))}
        logger.debug("package URIs: %s ", list(packages.values()))
        for package_name, uri in packages.items():
            package_uri = uri.strip().split("gs://{bucket}/".format(bucket=bucket.name))[1]
            blob = bucket.blob(package_uri)
            if not blob.exists():
                logger.warning("blob %s does not exist on Google Storage, uploading...", blob)
                blob.upload_from_filename(os.path.join(dir_path, 'packages', package_name))
                logger.info("blob %s available on Google Storage", blob)
            else:
                logger.info("blob %s does exist on Google Storage, re-uploading...", blob)
                blob.delete()
                blob.upload_from_filename(os.path.join(dir_path, 'packages', package_name))
                logger.info("blob %s available on Google Storage", blob)

    startTime = datetime.now()
    logger.info("PROCESS BEGINS")

    # START TASK
    logger.info("TASK %s", args.task)

    if args.task == 'preprocess':
        m = MyModel(project)
        m.preprocess()
        code=0

    elif args.task == 'check_model':
        code = random.randint(0,1)

    elif args.task == 'train':

        if ENV == 'cloud':
            # Instantiate ml engine
            ml_engine_service = discovery.build('ml', 'v1', credentials=credentials, cache_discovery=False)

            job_parent = "projects/{project}".format(project=project)

            now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")

            logger.info('Start training on the cloud')
            job_id = "template_{}_{}".format(account_id, now_str)
            job_body = {'trainingInput':
                        {'pythonVersion': parameters.ml_pythonVersion,
                         'runtimeVersion': parameters.ml_runtimeVersion,
                         'scaleTier': parameters.ml_train['ml_scaleTier'],
                         'masterType': parameters.ml_train['ml_masterType'],
                         'region': parameters.ml_region,
                         'pythonModule': 'mymodel.model',
                         'args': ["--project", project,
                                  "--task", "train"
                                 ],
                         'packageUris': list(packages.values())
                         },
                        'jobId': job_id}

            logging.info("job_body: %s", job_body)
            logging.info("job_parent: %s", job_parent)
            logging.info("creating a job ml: %s", job_id)
            job_ml = ml_engine_service.projects().jobs().create(parent=job_parent, body=job_body).execute()
            time.sleep(5)

            try:
                succeeded_job = is_success(ml_engine_service, project, job_id)
                if succeeded_job:
                    logger.info('Training job done')
                else:
                    logger.error('Training job failed')
                    sys.exit(1)
            except Exception as e:
                logger.error(e)
                sys.exit(1)

        elif ENV == 'local':
            m = MyModel(project)
            m.train()
        code=0

    elif args.task == 'verify_model':
        accuracy = random.random() + 0.5
        if accuracy >= 0.75:
            logger.info("Model Accuracy: %d%% --> OK", int(accuracy*100))
            code=0
        else:
            logger.info("Model Accuracy: %d%% --> Not OK", int(accuracy*100))
            code=1

    elif args.task == 'predict':
        m = MyModel(project)
        m.predict()
        code=0

    logger.info("TASK %s DONE", args.task)

    logger.info("PROCESS ENDED (TOOK %s)", str(datetime.now() - startTime))
    sys.exit(code)
