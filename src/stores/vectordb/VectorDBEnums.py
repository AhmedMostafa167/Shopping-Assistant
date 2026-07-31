from enum import Enum

class VectorDBEnums(Enum):
    PGVECTOR = "pgvector"
    

class PGVectoDistanceMethodEnums(Enum):
    COSINE = "vector_cosine_ops"
    DOT = "vector_ip_ops"
    

class PGVectorTableSchemaEnums(Enum):
    ID = "id"
    TEXT = "text"
    VECTOR = "vector"
    METADATA = "metadata"
    PRODUCT_ID = "product_id"
    _PREFIX = "pgvector"
    
class PGVectorInexTypeEnums(Enum):
    HNSW = "hnsw"
    IVF_FLAT = "ivfflat"