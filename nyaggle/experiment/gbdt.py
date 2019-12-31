import os
import time
from collections import namedtuple
from more_itertools import first_true
from logging import getLogger, FileHandler, DEBUG
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.metrics import roc_auc_score, mean_squared_error
from sklearn.utils.multiclass import type_of_target

from nyaggle.model.cv import cv
from nyaggle.util import plot_importance


GBDTResult = namedtuple('LGBResult', ['predicted_oof', 'predicted_test', 'scores', 'models', 'importance', 'time'])


def experiment_gbdt(logging_directory: str, model_params: Dict[str, Any], id_column: str,
                    X_train: pd.DataFrame, y: pd.Series,
                    X_test: Optional[pd.DataFrame] = None,
                    eval: Optional[Callable] = None,
                    gbdt_type: str = 'lgbm',
                    fit_params: Optional[Dict[str, Any]] = None,
                    nfolds: int = 5,
                    overwrite: bool = True,
                    stratified: bool = False,
                    seed: int = 42,
                    categorical_feature: Optional[List[str]] = None,
                    submission_filename: str = 'submission.csv'):
    """
    Evaluate metrics by cross-validation and stores result
    (log, oof prediction, test prediction, feature importance plot and submission file)
    under the directory specified.

    LGBMClassifier or LGBMRegressor with early-stopping is used (dispatched by ``type_of_target(y)``).

    Args:
        logging_directory:
            Path to directory where output of experiment is stored.
        model_params:
            Parameters passed to the constructor of the classifier/regressor object (i.e. LGBMRegressor).
        fit_params:
            Parameters passed to the fit method of the estimator.
        id_column:
            The name of index or column which is used as index.
            If `X_test` is not None, submission file is created along with this column.
        X_train:
            Training data. Categorical feature should be casted to pandas categorical type or encoded to integer.
        y:
            Target
        X_test:
            Test data (Optional). If specified, prediction on the test data is performed using ensemble of models.
        eval:
            Function used for logging and calculation of returning scores.
            This parameter isn't passed to GBDT, so you should set objective and eval_metric separately if needed.
        gbdt_type:
            Type of gradient boosting library used. "lgbm" (lightgbm) or "cat" (catboost)
        nfolds:
            Number of splits
        overwrite:
            If True, contents in ``logging_directory`` will be overwritten.
        stratified:
            If true, use stratified K-Fold
        seed:
            Seed used by the random number generator in ``KFold``
        categorical_feature:
            List of categorical column names. If ``None``, categorical columns are automatically determined by dtype.
        submission_filename:
            The name of submission file created under logging directory.
    :return:
        Namedtuple with following members

        * predicted_oof:
            numpy array, shape (len(X_train),) Predicted value on Out-of-Fold validation data.
        * predicted_test:
            numpy array, shape (len(X_test),) Predicted value on test data. ``None`` if X_test is ``None``
        * scores:
            list of float, shape(nfolds+1) ``scores[i]`` denotes validation score in i-th fold.
            ``scores[-1]`` is overall score. `None` if eval is not specified
        * models:
            list of objects, shape(nfolds) Trained models for each folds.
        * importance:
            pd.DataFrame, feature importance (average over folds, type="gain").
        * time:
            Training time in seconds.
    """
    start_time = time.time()

    if id_column in X_train.columns:
        if X_test is not None:
            assert list(X_train.columns) == list(X_test.columns)
            X_test.set_index(id_column, inplace=True)
        X_train.set_index(id_column, inplace=True)
        
    assert X_train.index.name == id_column, "index does not match"

    os.makedirs(logging_directory, exist_ok=overwrite)

    logger = getLogger(__name__)
    logger.setLevel(DEBUG)
    logger.addHandler(FileHandler(os.path.join(logging_directory, 'log.txt')))

    logger.info('GBDT: {}'.format(gbdt_type))
    logger.info('Experiment: {}'.format(logging_directory))
    logger.info('Params: {}'.format(model_params))
    logger.info('Features: {}'.format(list(X_train.columns)))

    if categorical_feature is None:
        categorical_feature = [c for c in X_train.columns if X_train[c].dtype.name in ['object', 'category']]
    logger.info('Categorical: {}'.format(categorical_feature))

    target_type = type_of_target(y)
    model, eval, cat_param_name, get_feature_importance = _dispatch_gbdt(gbdt_type, target_type, eval)
    models = [model(**model_params) for _ in range(nfolds)]

    if target_type not in ('binary', 'multiclass'):
        stratified = False

    importances = []

    def callback(fold: int, model: LGBMClassifier, x_train: pd.DataFrame, y: pd.Series):
        df = pd.DataFrame({
            'feature': list(x_train.columns),
            'importance': get_feature_importance(model)
        })
        importances.append(df)

    if fit_params is None:
        fit_params = {}
    if cat_param_name is not None and cat_param_name not in fit_params:
        fit_params[cat_param_name] = categorical_feature

    result = cv(models, X_train=X_train, y=y, X_test=X_test, nfolds=nfolds, logger=logger,
                on_each_fold=callback, eval=eval, stratified=stratified, seed=seed,
                fit_params=fit_params)

    importance = pd.concat(importances)

    importance = importance.groupby('feature')['importance'].mean().reset_index()
    importance.sort_values(by='importance', ascending=False, inplace=True)

    plot_importance(importance, os.path.join(logging_directory, 'feature_importance.png'))

    # save oof
    np.save(os.path.join(logging_directory, 'oof'), result.predicted_oof)
    np.save(os.path.join(logging_directory, 'test'), result.predicted_test)

    submit = pd.DataFrame({
        id_column: X_test.index,
        y.name: result.predicted_test
    })
    submit.to_csv(os.path.join(logging_directory, submission_filename), index=False)

    elapsed_time = time.time() - start_time

    return GBDTResult(result.predicted_oof, result.predicted_test, result.scores, models, importance, elapsed_time)


def _get_importance_lgbm(model):
    return model.booster_.feature_importance(importance_type='gain')


def _get_importance_cat(model):
    return model.get_feature_importance()


def _dispatch_gbdt(gbdt_type: str, target_type: str, custom_eval: Optional[Callable] = None):
    gbdt_table = [
        ('binary', 'lgbm', LGBMClassifier, roc_auc_score, 'categorical_feature', _get_importance_lgbm),
        ('continuous', 'lgbm', LGBMRegressor, mean_squared_error, 'categorical_feature', _get_importance_lgbm),
        ('binary', 'cat', CatBoostClassifier, roc_auc_score, 'cat_features', _get_importance_cat),
        ('continuous', 'cat', CatBoostRegressor, mean_squared_error, 'cat_features', _get_importance_cat),
    ]
    found = first_true(gbdt_table, pred=lambda x: x[0] == target_type and x[1] == gbdt_type)
    if found is None:
        raise RuntimeError('Not supported gbdt_type ({}) or type_of_target ({}).'.format(gbdt_type, target_type))

    model, eval, cat_param, get_importance = found[2], found[3], found[4], found[5]
    if custom_eval is not None:
        eval = custom_eval

    return model, eval, cat_param, get_importance
