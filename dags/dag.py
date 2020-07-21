import logging
from datetime import timedelta, datetime

import yaml
import subprocess

from airflow.models import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.python_operator import BranchPythonOperator

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

def check_branch(**kwargs):

    bash_command = [kwargs['python_path'],
                    kwargs['jobs_path'] + "/main.py",
                    "--account_id",
                    kwargs['account_id'],
                    "--task",
                    kwargs['task_code'],
                    "--conf",
                    kwargs['conf_code']]
    logging.info(" ".join(bash_command))
    cp = subprocess.run(bash_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logging.info("%s", cp.stdout)
    logging.info("Job return code : %s --> task %s", cp.returncode, kwargs.get(str(cp.returncode), "UNDEFINED"))
    return kwargs.get(str(cp.returncode), "UNDEFINED")


class DagBuilder:
    CONF_CODE = "/path/to/template.yaml"
    PYTHON_VENV_PATH = "/venv/bin/python"
    PYTHON_JOBS_PATH = "/src"

    def __init__(self):

        with open(DagBuilder.CONF_CODE, "r") as yaml_config:
            conf = yaml.load(yaml_config)
            self.path = conf['path']

        self.das_python_path = self.path + DagBuilder.PYTHON_VENV_PATH
        self.das_jobs_path = self.path + DagBuilder.PYTHON_JOBS_PATH

    def __get_accounts(self):
        return [ '000000' ]

    def create_template_dag(self, dag_id):
        default_args = {
            'owner': '🦄',
            'depends_on_past': False
        }

        _dag = DAG(
            dag_id=dag_id,
            schedule_interval=None,
            start_date=datetime(2020, 1, 1),
            default_args=default_args,
            max_active_runs=1,
            catchup=False
        )

        return _dag

    def create_template_task(self, dag_id, account_id, task, env='local'):

        execute_command = self.das_python_path + " " +\
                          self.das_jobs_path + "/main.py" +\
                          " --account_id {}".format(account_id) +\
                          " --task {}".format(task) +\
                          " --env {}".format(env) +\
                          " --conf {}".format(DagBuilder.CONF_CODE)
                          # " --date {}".format('{{ ds }}') +\

        execute = BashOperator(
            task_id=task,
            bash_command=execute_command,
            depends_on_past=True,
            retries=3,
            retry_delay=timedelta(minutes=3),
            dag=globals()[dag_id])

        return execute

    def create_account_dags(self):
        accounts = self.__get_accounts()
        template_dag_id = "template_{}"

        for account_id in accounts:

            dag_id = template_dag_id.format(account_id)

            globals()[dag_id] = self.create_template_dag(dag_id)

            task_start = DummyOperator(task_id="start", dag=globals()[dag_id])

            task_preprocess = self.create_template_task(dag_id, account_id, 'preprocess')
            task_train_skip = DummyOperator(task_id="train_skip", dag=globals()[dag_id])

            task_train = self.create_template_task(dag_id, account_id, 'train')#, 'cloud')

            task_check_model = BranchPythonOperator(task_id="check_model",
                                                    python_callable=check_branch,
                                                    op_kwargs={'account_id': account_id,
                                                               'task_code': 'check_model', # DO NOT CALL THIS ARGUMENT task, IT IS RESERVED!
                                                               '1': "train",
                                                               '0': "train_skip",
                                                               'python_path':self.das_python_path,
                                                               'jobs_path':self.das_jobs_path,
                                                               'conf_code':DagBuilder.CONF_CODE},
                                                    provide_context=True,
                                                    dag=globals()[dag_id])

            task_predict = self.create_template_task(dag_id, account_id, 'predict')

            task_end = DummyOperator(task_id="end", dag=globals()[dag_id])

            task_verify_model = BranchPythonOperator(task_id="verify_model",
                                                     python_callable=check_branch,
                                                     op_kwargs={'account_id': account_id,
                                                                'task_code': 'verify_model',
                                                                '1': "end",
                                                                '0': "predict",
                                                                'python_path':self.das_python_path,
                                                                'jobs_path':self.das_jobs_path,
                                                                'conf_code':DagBuilder.CONF_CODE},
                                                     provide_context=True,
                                                     dag=globals()[dag_id],
                                                     trigger_rule='none_failed')

            task_start >> task_preprocess >> task_check_model >> [ task_train_skip, task_train ] >> task_verify_model >> [ task_predict, task_end ]
            task_predict >> task_end

dag_builder = DagBuilder()
dag_builder.create_account_dags()
