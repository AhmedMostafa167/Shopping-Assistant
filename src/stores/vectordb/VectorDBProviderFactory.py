from .providers import PGVectorProvider
from .VectorDBEnums import VectorDBEnums, PGVectorDistanceMethodEnums
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
                # Must match the operator used in search (<=> is cosine distance).
                distance_method=PGVectorDistanceMethodEnums.COSINE.value,
                )