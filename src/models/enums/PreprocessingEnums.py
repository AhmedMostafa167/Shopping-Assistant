from enum import Enum


class PreprocessingEnums(Enum):
    DATA_PREPROCESSING_SUCESS = "data_preprocessing_success"
    DATA_PREPROCESSING_FAILED = "data_preprocessing_failed"
    DATA_VALIDATION_FAILED = "data_validation_failed"
    DATA_VALIDATION_SUCCESS = "data_validation_success"
    DATA_VALIDATION_DONE_WITH_ERRORS = "data_validation_done_with_errors"