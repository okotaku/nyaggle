import pandas as pd

from sklearn.metrics import log_loss
from nyaggle.experiment import experiment_gbdt


X_train = pd.read_csv('train.csv', index_col='ID')
X_test = pd.read_csv('test.csv', index_col='ID')
y_train = X_train['target']
X_train = X_train.drop('target', axis=1)

cat_params = {
    'eval_metric': 'Logloss',
    'loss_function': 'Logloss',
    'metric_period': 10,
    'depth': 8,
}

result = experiment_gbdt(cat_params, X_train, y_train, X_test, logging_directory='bnp-paribas-{time}',
                         eval_func=log_loss,
                         gbdt_type='cat',
                         sample_submission=pd.read_csv('sample_submission.csv'),
                         with_mlflow=True)