from enum import Enum


class ResponseEnums(Enum):
    FILE_VALIDATION_SUCESS = "file_validation_success"
    FILE_TYPE_NOT_SUPPORTED = "file_type_not_supported"
    FILE_SIZE_EXCEEDED = "file_type_exceeded" 
    FILE_UPLOAD_SUCESS = "file_upload_success"
    FILE_UPLOAD_FAILED = "file_upload_failed"
    PRODUCT_INSERTION_FAILED = "product_insertion_failed"
    PRODUCT_INSERTION_SUCCESS = "product_insertion_success"
    ASSET_NOT_FOUND = "asset_not_found"
    