import sys
import logging
import argparse
import mymodel.parameters as param

logger = logging.getLogger(__name__)


class MyModel:
    def __init__(self, project):
        super(MyModel, self).__init__()
        self.project = project

    def preprocess(self):
        logger.info("PREPROCESSING...")
        logger.info("PREPROCESSING OK")

    def train(self):
        logger.info("TRAINING...")
        logger.info("PARAMETERS: %s, %s", param.param1, param.param2)
        logger.info("TRAINING OK")

    def predict(self):
        logger.info("PREDICT...")
        logger.info("PREDICT OK")

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="MODEL", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--project", dest="project", help="GCP Project Account")
    parser.add_argument("--task", dest="task", choices=['preprocess', 'train', 'test'], help="Task to perform")

    if len(sys.argv) < 5:
        parser.print_help()
        sys.exit(1)
    args = parser.parse_args()

    m = MyModel(args.project)

    if args.task == 'preprocess':
        m.preprocess()

    elif args.task == 'train':
        m.train()

    elif args.task == 'predict':
        m.predict()
