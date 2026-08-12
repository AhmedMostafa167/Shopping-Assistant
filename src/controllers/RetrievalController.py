from .BaseController import BaseController
from .EmbeddingsController import EmbeddingsController
from models.enums import DataBaseEnums
from ..models import ProductModel
from ..utils import rrf
class RetrievalController(BaseController):
    def __init__(self, embedding_client, vectordb_client):
        super().__init__()
        
        self.product_model = ProductModel()
        self.embedding_client = embedding_client
        self.vectordb_client = vectordb_client
    async def keyword_search(self, query: str, top_k: int = 10):
        products = await self.product_model.keyword_search(query, top_k)
        products = sorted(products, key=lambda x: x.score, reverse=True)

        return products
    
    async def vector_search(self, vector: list, top_k: int = 10, 
                            category_name: str=DataBaseEnums.DEFAULT_CATEGORY_NAME.value):
        
        query_embedding = self.embedding_client.embed_texts(texts=[vector], batch_size=1)
        
        
        embeddings_contoller = EmbeddingsController(self.vectordb_client, self.embedding_client)
        table_name = embeddings_contoller.create_table_name(self.category_name)
        products = await self.vectordb_client.search_by_vector(table_name=table_name, 
                                                       vector=query_embedding[0], 
                                                       limit=top_k, category_name=category_name)
        products = sorted(products, key=lambda x: x.score, reverse=True)
        return products
    
    def reranking(self, vector_results, keyword_results, k=60):
        return rrf(vector_results, keyword_results, k=k)
    
    async def get_products_by_ids(self, product_ids: list[int]):
        return await self.product_model.get_products_by_ids(product_ids)
    