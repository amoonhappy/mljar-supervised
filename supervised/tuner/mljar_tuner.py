import numpy as np
import pandas as pd
import copy

from supervised.tuner.random_parameters import RandomParameters
from supervised.algorithms.registry import AlgorithmsRegistry
from supervised.tuner.preprocessing_tuner import PreprocessingTuner
from supervised.tuner.hill_climbing import HillClimbing
from supervised.algorithms.registry import (
    BINARY_CLASSIFICATION,
    MULTICLASS_CLASSIFICATION,
    REGRESSION,
)

import logging
from supervised.utils.config import LOG_LEVEL

logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)


class MljarTuner:
    def __init__(self, tuner_params, algorithms, ml_task, validation, seed):
        logger.debug("MljarTuner.__init__")
        self._start_random_models = tuner_params.get("start_random_models", 5)
        self._hill_climbing_steps = tuner_params.get("hill_climbing_steps", 3)
        self._top_models_to_improve = tuner_params.get("top_models_to_improve", 3)
        self._algorithms = algorithms
        self._ml_task = ml_task
        self._validation = validation
        self._seed = seed

        self._unique_params_keys = []

    def get_not_so_random_params(self, X, y):
        models_cnt = 0
        generated_params = []
        for model_type in self._algorithms:
            for i in range(self._start_random_models):
                logger.info("Generate parameters for model #{0}".format(models_cnt + 1))
                params = self._get_model_params(model_type, X, y, models_cnt + 1)
                if params is None:
                    continue
                params["name"] = f"model_{models_cnt + 1}"

                unique_params_key = MljarTuner.get_params_key(params)
                if unique_params_key not in self._unique_params_keys:
                    generated_params += [params]
                    self._unique_params_keys += [unique_params_key]
                    models_cnt += 1
        return generated_params

    def get_hill_climbing_params(self, current_models):

        # second, hill climbing
        for _ in range(self._hill_climbing_steps):
            # get models orderer by loss
            # TODO: refactor this callbacks.callbacks[0]
            models = sorted(
                [(m.callbacks.callbacks[0].final_loss, m) for m in current_models],
                key=lambda x: x[0],
            )
            for i in range(min(self._top_models_to_improve, len(models))):
                m = models[i][1]
                for p in HillClimbing.get(
                    m.params.get("learner"),
                    self._ml_task,
                    len(current_models) + self._seed,
                ):
                    logger.info(
                        "Hill climbing step, for model #{0}".format(
                            len(current_models) + 1
                        )
                    )
                    if p is not None:
                        all_params = copy.deepcopy(m.params)
                        all_params["learner"] = p
                        all_params["name"] = f"model_{len(current_models) + 1}"

                        unique_params_key = MljarTuner.get_params_key(all_params)
                        if unique_params_key not in self._unique_params_keys:
                            self._unique_params_keys += [unique_params_key]
                            yield all_params

    def _get_model_params(self, model_type, X, y, models_cnt):
        model_info = AlgorithmsRegistry.registry[self._ml_task][model_type]
        model_params = RandomParameters.get(
            model_info["params"], models_cnt + self._seed
        )
        required_preprocessing = model_info["required_preprocessing"]
        model_additional = model_info["additional"]
        preprocessing_params = PreprocessingTuner.get(
            required_preprocessing, {"train": {"X": X, "y": y}}, self._ml_task
        )

        model_params = {
            "additional": model_additional,
            "preprocessing": preprocessing_params,
            "validation": self._validation,
            "learner": {
                "model_type": model_info["class"].algorithm_short_name,
                "ml_task": self._ml_task,
                **model_params,
            },
        }
        num_class = (
            len(np.unique(y[~pd.isnull(y)]))
            if self._ml_task == MULTICLASS_CLASSIFICATION
            else None
        )
        if num_class is not None:
            model_params["learner"]["num_class"] = num_class

        model_params["ml_task"] = self._ml_task

        return model_params

    @staticmethod
    def get_params_key(params):
        key = "key_"
        for main_key in ["additional", "preprocessing", "validation", "learner"]:
            key += main_key
            for k, v in params[main_key].items():
                key += "_{}_{}".format(k, v)
        return key
