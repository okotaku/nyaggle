import os
import os
import tempfile

import pandas as pd
from sklearn.metrics import roc_auc_score, mean_squared_error, mean_absolute_error
from sklearn.model_selection import train_test_split

from nyaggle.experiment import experiment_gbdt
from nyaggle.testing import make_classification_df, make_regression_df


def test_experiment_lgb_classifier():
    X, y = make_classification_df(n_samples=1024, n_num_features=10, n_cat_features=2,
                                  class_sep=0.98, random_state=0, id_column='user_id')

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.5)

    params = {
        'objective': 'binary',
        'max_depth': 8
    }

    with tempfile.TemporaryDirectory() as temp_path:
        result = experiment_gbdt(temp_path, params, 'user_id',
                                 X_train, y_train, X_test, roc_auc_score, stratified=True)

        assert roc_auc_score(y_train, result.predicted_oof) >= 0.85
        assert roc_auc_score(y_test, result.predicted_test) >= 0.85

        assert os.path.exists(os.path.join(temp_path, 'submission.csv'))
        assert os.path.exists(os.path.join(temp_path, 'oof.npy'))
        assert os.path.exists(os.path.join(temp_path, 'test.npy'))


def test_experiment_lgb_regressor():
    X, y = make_regression_df(n_samples=1024, n_num_features=10, n_cat_features=2,
                              random_state=0, id_column='user_id')

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.5)

    params = {
        'objective': 'regression',
        'max_depth': 8
    }

    with tempfile.TemporaryDirectory() as temp_path:
        result = experiment_gbdt(temp_path, params, 'user_id',
                                 X_train, y_train, X_test, stratified=True)

        assert mean_squared_error(y_train, result.predicted_oof) == result.scores[-1]
        assert os.path.exists(os.path.join(temp_path, 'submission.csv'))
        assert os.path.exists(os.path.join(temp_path, 'oof.npy'))
        assert os.path.exists(os.path.join(temp_path, 'test.npy'))


def test_experiment_cat_classifier():
    X, y = make_classification_df(n_samples=1024, n_num_features=10, n_cat_features=2,
                                  class_sep=0.98, random_state=0, id_column='user_id', target_name='tgt')

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.5)

    params = {
        'max_depth': 8,
        'num_boost_round': 100
    }

    with tempfile.TemporaryDirectory() as temp_path:
        result = experiment_gbdt(temp_path, params, 'user_id',
                                 X_train, y_train, X_test, roc_auc_score, stratified=True, gbdt_type='cat')

        assert roc_auc_score(y_train, result.predicted_oof) >= 0.85
        assert roc_auc_score(y_test, result.predicted_test) >= 0.85

        assert os.path.exists(os.path.join(temp_path, 'submission.csv'))
        assert list(pd.read_csv(os.path.join(temp_path, 'submission.csv')).columns) == ['user_id', 'tgt']

        assert os.path.exists(os.path.join(temp_path, 'oof.npy'))
        assert os.path.exists(os.path.join(temp_path, 'test.npy'))


def test_experiment_cat_regressor():
    X, y = make_regression_df(n_samples=1024, n_num_features=10, n_cat_features=2,
                              random_state=0, id_column='user_id')

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.5)

    params = {
        'max_depth': 8,
        'num_boost_round': 100
    }

    with tempfile.TemporaryDirectory() as temp_path:
        result = experiment_gbdt(temp_path, params, 'user_id',
                                 X_train, y_train, X_test, stratified=True, gbdt_type='cat')

        assert mean_squared_error(y_train, result.predicted_oof) == result.scores[-1]
        assert os.path.exists(os.path.join(temp_path, 'submission.csv'))
        assert os.path.exists(os.path.join(temp_path, 'oof.npy'))
        assert os.path.exists(os.path.join(temp_path, 'test.npy'))


def test_experiment_cat_custom_eval():
    X, y = make_regression_df(n_samples=1024, n_num_features=10, n_cat_features=2,
                              random_state=0, id_column='user_id')

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.5)

    params = {
        'max_depth': 8,
        'num_boost_round': 100,
        'eval_metric': 'MAE'
    }

    with tempfile.TemporaryDirectory() as temp_path:
        result = experiment_gbdt(temp_path, params, 'user_id',
                                 X_train, y_train, X_test, stratified=True, gbdt_type='cat', eval=mean_absolute_error)

        assert mean_absolute_error(y_train, result.predicted_oof) == result.scores[-1]
