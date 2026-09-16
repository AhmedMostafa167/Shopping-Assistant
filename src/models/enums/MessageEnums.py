from enum import Enum


class MessageEnums(str, Enum):
    AGENT_EXECUTION_FAILED = "agent_execution_failed"
    USER_PROFILE_NOT_FOUND = "user_profile_not_found"
    CONVERSATION_NOT_FOUND = "conversation_not_found"
    FILE_UPLOAD_FAILED = "file_upload_failed"
    FILE_UPLOAD_SUCCESS = "file_upload_success"
    ASSET_NOT_FOUND = "asset_not_found"
    PRODUCT_INSERTION_FAILED = "product_insertion_failed"
    PRODUCT_INSERTION_SUCCESS = "product_insertion_success"
    PRODUCT_RETRIEVAL_FAILED = "product_retrieval_failed"
    PRODUCT_RETRIEVAL_SUCCESS = "product_retrieval_success"
    NO_PRODUCTS_FOUND = "no_products_found"
    VECTOR_INDEXING_SUCCESS = "vector_indexing_success"
    INVALID_SEARCH_QUERY = "invalid_search_query"


class LogEventEnums(str, Enum):
    APPLICATION_STARTING = "application_starting"
    APPLICATION_STARTED = "application_started"
    APPLICATION_STOPPED = "application_stopped"
    DATABASE_READY = "database_ready"
    VECTOR_STORE_CONNECTED = "vector_store_connected"
    VECTOR_STORE_DISCONNECTED = "vector_store_disconnected"
    CONVERSATION_CREATED = "conversation_created"
    CHAT_REQUEST_STARTED = "chat_request_started"
    CHAT_REQUEST_COMPLETED = "chat_request_completed"
    AGENT_EXECUTION_FAILED = "agent_execution_failed"
    FILE_UPLOAD_FAILED = "file_upload_failed"
    FILE_UPLOAD_COMPLETED = "file_upload_completed"
    DATA_VALIDATION_COMPLETED = "data_validation_completed"
    PRODUCT_INSERTION_FAILED = "product_insertion_failed"
    VECTOR_INDEXING_COMPLETED = "vector_indexing_completed"
    RETRIEVAL_COMPLETED = "retrieval_completed"
    MEMORY_EXTRACTION_FAILED = "memory_extraction_failed"
    MEMORY_CONFLICT_PARSE_FAILED = "memory_conflict_parse_failed"
