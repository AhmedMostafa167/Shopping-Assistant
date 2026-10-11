from .BaseController import BaseController
import json
from models.db_schemes import Product
from stores.llm.LLMEnums import DocumentTypeEnum

# The most inputs Cohere accepts in one embedding request.
EMBEDDING_BATCH_SIZE = 96


class EmbeddingsController(BaseController):
    def __init__(self, vectordb_client, embedding_client):
        super().__init__()
        
        self.vectordb_client = vectordb_client
        self.embedding_client = embedding_client
    def create_table_name(self, category_name: str):
        return f"table_{self.vectordb_client.default_vector_size}_{category_name}".strip()

    async def delete_vectordb_table(self, category_name: str):
        table_name = self.create_table_name(category_name)
        await self.vectordb_client.delete_table(table_name) 
        
    async def get_vectordb_table_info(self, category_name: str):
        table_name = self.create_table_name(category_name)
        table_info =  await self.vectordb_client.get_table_info(table_name)
        
        return json.loads(
            json.dumps(table_info, default=lambda o: o.__dict__)
        )
        
    @staticmethod
    def build_embedding_text(product: Product) -> str:
        return f"{product.title}\n{product.description}"

    async def index_missing_products(self, category_name: str, product_model,
                                     max_products: int | None = None,
                                     batch_size: int = EMBEDDING_BATCH_SIZE) -> dict:
        """Embed and store every product of the category that has no embedding yet.

        Works in small batches, each saved before the next one is embedded, so a failure
        loses at most one batch of paid embedding calls and a re-run continues where the
        last one stopped. Returns how many were embedded and how many remain.
        """
        table_name = self.create_table_name(category_name)
        await self.vectordb_client.create_table(
            table_name=table_name,
            embedding_size=self.vectordb_client.default_vector_size,
        )

        embedded = 0
        while max_products is None or embedded < max_products:
            limit = batch_size if max_products is None else min(batch_size, max_products - embedded)
            products = await product_model.get_products_without_embedding(
                category_name=category_name, vector_table_name=table_name, limit=limit
            )
            if not products:
                break

            texts = [self.build_embedding_text(product) for product in products]
            vectors = await self.embedding_client.aembed_texts(
                texts=texts, document_type=DocumentTypeEnum.DOCUMENT.value
            )
            if vectors is None or len(vectors) != len(texts):
                raise RuntimeError("embedding_client_returned_no_vectors")

            inserted = await self.vectordb_client.insert_many(
                table_name=table_name,
                texts=texts,
                vectors=vectors,
                record_ids=[product.product_id for product in products],
                batch_size=batch_size,
            )
            if not inserted:
                raise RuntimeError("vector_insert_failed")

            embedded += len(products)

        remaining = await product_model.count_products_without_embedding(
            category_name=category_name, vector_table_name=table_name
        )
        # Skipped by the store when the index already exists or the table is still small;
        # once built, new rows are added to it automatically.
        await self.vectordb_client.create_vector_index(table_name=table_name)
        return {"embedded": embedded, "remaining": remaining}
