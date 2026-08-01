from .BaseController import BaseController
import json
from typing import List
from models.db_schemes import Product
from stores.llm.LLMEnums import DocumentTypeEnum
class RAGController(BaseController):
    def __init__(self, vectordb_client, generatation_client, embedding_client):
        super().__init__()
        
        self.vectordb_client = vectordb_client
        self.generatation_client = generatation_client
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
        
    async def index_into_vectordb(self, category_name: str, products: List[Product], do_reset: bool = False):
        table_name = self.create_table_name(category_name)
        
        #extract embedding columns
        title = [product.title for product in products]
        description = [product.description for product in products]
        embedding_text = [f"{title[i]}\n{description[i]}" for i in range(len(title))]
        
        # embedd title+description
        vectors = await self.embedding_client.embed_text(text=embedding_text, document_type=DocumentTypeEnum.DOCUMENT.value)
        
        # create pgtable
        _ = await self.vectordb_client.create_table(table_name=table_name, 
                                                    embedding_size=self.vectordb_client.default_vector_size, 
                                                    do_reset=do_reset)
        
        # insert into pgtable
        _ = await self.vectordb_client.insert_many(table_name=table_name, 
                                               texts=embedding_text, 
                                               vectors=vectors, 
                                               record_is=[product.product_id for product in products],
                                               batch_size=100)
        
        return True