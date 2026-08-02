from .providers import PGVectorProvider
from .VectorDBEnums import VectorDBEnums, PGVectorInexTypeEnums
from controllers.BaseController import BaseController
from sqlalchemy.orm import sessionmaker

class VectorDBProviderFactory:
    def __init__(self, config, db_client: sessionmaker=None):
        self.config = config
        self.db_client = db_client
        self.base_controller = BaseController()
        
        
    def create(self, provider: str = VectorDBEnums.PGVECTOR.value):
        
        
        if provider == VectorDBEnums.PGVECTOR.value:
            return PGVectorProvider(
                self.db_client,
                default_vector_size=self.config.EMBEDDING_MODEL_SIZE,
                distance_method=PGVectorInexTypeEnums.HNSW.value,
                index_threshold=self.config.VECTOR_DB_BACKEND
                )