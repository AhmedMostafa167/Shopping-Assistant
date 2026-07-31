from enum import Enum


class PreprocessingEnums(Enum):
    DATA_PREPROCESSING_SUCESS = "data_preprocessing_success"
    DATA_PREPROCESSING_FAILED = "data_preprocessing_failed"
    DATA_VALIDATION_FAILED = "deleted_invalid_rows"
    DATA_VALIDATION_SUCCESS = "data_validation_success"