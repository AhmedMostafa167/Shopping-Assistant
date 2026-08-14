from .BaseController import BaseController
from .EmbeddingsController import EmbeddingsController
from models.enums import DataBaseEnums
from models import ProductModel
from utils import rrf
from pydantic import BaseModel

class RetrievalController(BaseController):
    def __init__(self, embedding_client, vectordb_client, reranking_client, db_client):
        super().__init__()
        
        self.product_model = ProductModel(db_client)
        self.embedding_client = embedding_client
        self.vectordb_client = vectordb_client
        self.reranking_client = reranking_client
    async def keyword_search(self, query: str, top_k: int = 10):
        products = await self.product_model.keyword_search(query, top_k)
        products = sorted(products, key=lambda x: x.score, reverse=True)

        return products
    
    async def vector_search(self, texts: list, top_k: int = 10, 
                            category_name: str=DataBaseEnums.DEFAULT_CATEGORY_NAME.value):
    
        query_embedding = self.embedding_client.embed_texts(texts=texts, batch_size=1)
        
        
        embeddings_contoller = EmbeddingsController(self.vectordb_client, self.embedding_client)
        table_name = embeddings_contoller.create_table_name(category_name)
        products = await self.vectordb_client.search_by_vector(table_name=table_name, 
                                                       vector=query_embedding[0], 
                                                       limit=top_k, category_name=category_name)
        products = sorted(products, key=lambda x: x.score, reverse=True)
        return products
    
    def fuse_results(self, vector_results, keyword_results, k=60):
        return rrf(vector_results, keyword_results, k=k)
    
    async def rerank_results(self, retrieved_products: list, query: str):
        products = await self.product_model.get_products_by_ids([i[0] for i in retrieved_products])
        title = [product.title for product in products]
        description = [product.description for product in products]
        embedding_text = [f"{title[i]}\n{description[i]}" for i in range(len(title))]
        ranked_results = await self.reranking_client.rerank(retrieved_products=embedding_text, query=query)
        products = [products[i.index] for i in ranked_results]
        
        return products
    
    async def get_products_by_ids(self, product_ids: list[int]):
        return await self.product_model.get_products_by_ids(product_ids)
    
    
