from .BaseController import BaseController
from .EmbeddingsController import EmbeddingsController
from models.enums import DataBaseEnums
from models import ProductModel
from utils import rrf
from stores.llm.LLMEnums import DocumentTypeEnum


class RetrievalController(BaseController):
    def __init__(self, embedding_client, vectordb_client, db_client):
        super().__init__()

        self.embedding_client = embedding_client
        self.vectordb_client = vectordb_client
        self.db_client = db_client
        self.product_model = None
         
    @classmethod
    async def create_instance(cls, embedding_client, vectordb_client, db_client):
        controller = cls(embedding_client, vectordb_client, db_client)
        controller.product_model = await ProductModel.create_instance(db_client=db_client)
        return controller

    async def keyword_search(self, query: str, top_k: int = 10):
        products = await self.product_model.keyword_search(query, top_k)
        products = sorted(products, key=lambda x: x.score, reverse=True)

        return products

    async def vector_search(self, query: str, top_k: int = 10,
                             category_name: str = DataBaseEnums.DEFAULT_CATEGORY_NAME.value):

        query_embedding = self.embedding_client.embed_texts(
            texts=[query], document_type=DocumentTypeEnum.QUERY.value, batch_size=1
        )

        embeddings_controller = EmbeddingsController(self.vectordb_client, self.embedding_client)
        table_name = embeddings_controller.create_table_name(category_name)
        products = await self.vectordb_client.search_by_vector(
            table_name=table_name,
            vector=query_embedding[0],
            limit=top_k,
            category_name=category_name,
        )
        products = sorted(products, key=lambda x: x.score, reverse=True)
        return products

    def reranking(self, vector_results, keyword_results, k=60):
        return rrf(vector_results, keyword_results, k=k)

    async def get_products_by_ids(self, product_ids: list[int]):
        return await self.product_model.get_products_by_ids(product_ids)

    async def hybrid_search(self, query: str, top_k: int = 10,
                             category_name: str = DataBaseEnums.DEFAULT_CATEGORY_NAME.value):
        vector_results = await self.vector_search(query, top_k, category_name)
        keyword_results = await self.keyword_search(query, top_k)

        fused = self.reranking(vector_results, keyword_results)
        fused_ids = [pid for pid, _ in fused][:top_k]

        if not fused_ids:
            return []

        products = await self.get_products_by_ids(fused_ids)

        order = {pid: i for i, pid in enumerate(fused_ids)}
        return sorted(products, key=lambda p: order.get(p.product_id, len(order)))