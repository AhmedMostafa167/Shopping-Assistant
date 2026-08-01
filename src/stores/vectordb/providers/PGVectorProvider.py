from ..VectorDBInterface import VectorDBInterface
from ..VectorDBEnums import VectorDBEnums, PGVectoDistanceMethodEnums, PGVectorTableSchemaEnums, PGVectorInexTypeEnums
import logging
from typing import List
from ..VectorDBSchemes import VectorSearchResult
from sqlalchemy.sql import text as sql_text
import json

class PGVectorProvider(VectorDBInterface):
    def __init__(self, db_client, defualt_vector_size: int = 786, distance_method: str = None, index_threshold: int = 1000):
        
        self.db_client = db_client
        self.defualt_vector_size = defualt_vector_size
        self.distance_method = distance_method
        self.pgvector_table_prefix = PGVectorTableSchemaEnums._PREFIX.value
        self.logger = logging.getLogger("uvicorn")
        self.default_index_name = lambda table_name, index_type="vector": f"{table_name}_{index_type}_idx"
        self.index_threshold = index_threshold  
        
        
    async def connect(self):
        async with self.db_client() as session:
            async with session.begin():
                await session.execute(sql_text(f"CREATE EXTENSION IF NOT EXISTS vector;"))
            await session.commit()
            
    async def disconnect(self):
        pass
    async def is_table_existed(self, table_name: str) -> bool:
        record = None
        async with self.db_client() as session:
            query = sql_text("SELECT * FROM pg_tables WHERE tablename = :table_name")
            results = await session.execute(query, {"table_name": table_name})
            record = results.scalar_one_or_none()
            
            return record
            
    async def list_all_tables(self) -> List:
        tables = []
        async with self.db_client() as session:
            query = sql_text(f"SELECT tablename FROM pg_tables WHERE tablename like {self.pgvector_table_prefix}")
            results = await session.execute(query)
            tables = results.scalars().all()
            
        return tables
    
    async def get_table_info(self, table_name: str) -> dict:
        info = {}
        async with self.db_client() as session:
            tbl_info_query = sql_text(f'''
                             SELECT tablename, schemaname, tableowner, tablespace, hasindexes
                             FROM pg_tables
                             WHERE tablename = {table_name}
                             ''')
            num_records_query = sql_text(f"SELECT COUNT(*) FROM {table_name}")

            records = await session.execute(tbl_info_query)
            num_records = await session.execute(num_records_query)
            info = records.fetchone()
            
            if not info:
                return None
            
        
        return {
            "table_info": dict(info),
            "num_records": num_records.scalar_one_or_none()
        }
        
    async def delete_table(self, table_name: str):
        async with self.db_client() as session:
            async with session.begin():
                self.logger.info(f"Deleting table {table_name}")
                await session.execute(sql_text(f"DROP TABLE IF EXISTS :table_name"), {"table_name": table_name})
            await session.commit()
                
            return True
        
    async def create_table(self, table_name: str, 
                           embedding_size: int, 
                           do_reset: bool = False):
        
        if do_reset:
            await self.delete_table(table_name)
        if not await self.is_table_existed(table_name):
            async with self.db_client() as session:
                async with session.begin():
                    self.logger.info(f"Creating table: {table_name}")
                    await session.execute(sql_text(
                        f"CREATE TABLE {table_name} ("
                        f"{PGVectorTableSchemaEnums.ID.value} bigserial PRIMARY KEY,"
                        f'{PGVectorTableSchemaEnums.TEXT.value} text, '
                        f"{PGVectorTableSchemaEnums.VECTOR.value} vector({embedding_size}),"
                        f"{PGVectorTableSchemaEnums.METADATA.value} jsonb DEFAULT \'{{}}\',"
                        F"{PGVectorTableSchemaEnums.PRODUCT_ID.value} integer "
                        f"FOREIGN KEY ({PGVectorTableSchemaEnums.PRODUCT_ID.value}) REFERENCES products(product_id)"
                        ")"
                        ))
                await session.commit()
                    
                return True
            
            
    async def insert_one(self, table_name: str, 
                     text: str, vector: list,
                     metadata: dict = None, 
                     product_id: str = None):
        if not await self.is_table_existed(table_name):
            self.logger.info(f"Table {table_name} doesn't exist")
        if product_id is None:
            self.logger.info("Can't insert a record without a record id <this is a foriegn key>")
    
        async with self.db_client() as session:
            async with session.begin():
                self.logger.info(f"Inserting record {product_id} into table {table_name}")
                metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else "{}"
                await session.execute(sql_text(
                    f"INSERT INTO {table_name} ({PGVectorTableSchemaEnums.TEXT.value},{PGVectorTableSchemaEnums.VECTOR.value}, {PGVectorTableSchemaEnums.METADATA.value}, {PGVectorTableSchemaEnums.PRODUCT_ID.value}) VALUES (:text , :vector, :metadata, :product_id)"
                    ), {
                        "text": text,
                        "vector": "[" + ",".join([ str(v) for v in vector ]) + "]",
                        "metadata": metadata_json,
                        "product_id": product_id
                    })
                await session.commit()
                
            return True
        
    async def insert_many(self, table_name: str, 
                          texts: list, 
                          vectors: list, 
                          metadata: list = None, 
                          record_ids: list = None, 
                          batch_size: int = 50):
        
        is_table_existed = await self.is_table_existed(table_name)
        if not is_table_existed:
            self.logger.info(f"Table {table_name} doesn't exist")
            return False
        if len(vectors) != len(texts):
            self.logger.info(f"Number of vectors and texts must be equal")
            return False
        
        if not metadata or len(metadata) == 0:
            metadata = [None] * len(texts)
            
        async with self.db_client() as session:
            async with session.begin():
                for i in range(0, len(texts), batch_size):
                    batch_texts = texts[i:i+batch_size]
                    batch_vectors = vectors[i:i + batch_size]
                    batch_metadata = metadata[i:i + batch_size]
                    batch_record_ids = record_ids[i:i + batch_size]
        
                    values = []

                    for _text, _vector, _metadata, _record_id in zip(batch_texts, batch_vectors, batch_metadata, batch_record_ids):
                        
                        metadata_json = json.dumps(_metadata, ensure_ascii=False) if _metadata is not None else "{}"
                        values.append({
                            'text': _text,
                            'vector': "[" + ",".join([ str(v) for v in _vector ]) + "]",
                            'metadata': metadata_json,
                            'product_id': _record_id
                        })
                    
                    batch_insert_sql = sql_text(f'INSERT INTO {table_name} '
                                    f'({PGVectorTableSchemaEnums.TEXT.value}, '
                                    f'{PGVectorTableSchemaEnums.VECTOR.value}, '
                                    f'{PGVectorTableSchemaEnums.METADATA.value}, '
                                    f'{PGVectorTableSchemaEnums.PRODUCT_ID.value}) '
                                    f'VALUES (:text, :vector, :metadata, :product_id)')
                    
                    await session.execute(batch_insert_sql, values)
        return True
    
    async def search_by_vector(self, table_name: str, vector: list, limit: int, category_name: str) -> List[VectorSearchResult]:
        is_table_existed = await self.is_table_existed(table_name)
        if not is_table_existed:
            self.logger.info(f"Table {table_name} doesn't exist")
            return []
        
        vector = "[" + ",".join([ str(v) for v in vector ]) + "]"
        async with self.db_client() as session:
            async with session.begin():
                search_sql = sql_text(f'SELECT {PGVectorTableSchemaEnums.PRODUCT_ID.value} as product_id, 1 -({PGVectorTableSchemaEnums.VECTOR.value} <=> :vector) as score'
                                        f' FROM {table_name}'
                                        f' JOIN products USING ({PGVectorTableSchemaEnums.PRODUCT_ID.value})'
                                        f' WHERE products.category_name = :category_name'
                                        ' ORDER BY score DESC'
                                        f' LIMIT {limit}')
                results = await session.execute(search_sql, {
                                                             "category_name": category_name, 
                                                             "vector": vector
                                                            }
                                                )
                records = results.mappings().fetchall()
                
                return [
                    VectorSearchResult(
                        product_id=record["product_id"],
                        score=record["score"]
                    )
                    for record in records
                ]
            
            
    async def is_index_existed(self, table_name: str) -> bool:
        index_name = self.default_index_name(table_name)
        async with self.db_client() as session:
            query = sql_text(f"SELECT * FROM pg_indexes WHERE tablename = :table_name AND indexname = :index_name")
            results = await session.execute(query, {
                "table_name": table_name, 
                "index_name": index_name
                })
        
            return bool(results.scalar_one_or_none())

    async def create_vector_index(self, table_name: str,
                                  index_type: str = PGVectorInexTypeEnums.HNSW.value):
        is_index_existed = await self.is_index_existed(table_name)
        index_name = self.default_index_name(table_name)

        if is_index_existed:
            self.logger.info(f"Index {index_name} already exists")
            return False
        
        async with self.db_client() as session:
            async with session.begin():
                count_sql = sql_text(f'SELECT COUNT(*) FROM {table_name}')
                result = await session.execute(count_sql)
                records_count = result.scalar_one()

                if records_count < self.index_threshold:
                    return False
                        
                self.logger.info(f"Creating vector index for collection: {table_name}")
                
                create_index_sql = sql_text(f"CREATE INDEX {index_name} ON {table_name} USING {index_type} ({PGVectorTableSchemaEnums.VECTOR.value});")
                await session.execute(create_index_sql)
                self.logger.info(f"Vector Index created on {table_name}")
                
                
    async def reset_vector_index(self, table_name: str, 
                                       index_type: str = PGVectorInexTypeEnums.HNSW.value) -> bool:
        
        index_name = self.default_index_name(table_name)
        async with self.db_client() as session:
            async with session.begin():
                drop_sql = sql_text(f'DROP INDEX IF EXISTS {index_name}')
                await session.execute(drop_sql)
        
        return await self.create_vector_index(table_name=table_name, index_type=index_type)

    async def create_column_index(self, table_name: str, column_name: str) -> bool:
        index_name = self.default_index_name(table_name, column_name)
        is_existed = await self.is_index_existed(table_name, index_name)
        if is_existed:
            self.logger.info(f"Index {index_name} already exists")
            return False

        async with self.db_client() as session:
            async with session.begin():
                self.logger.info(f"Creating index on {table_name}.{column_name}")
                create_index_sql = sql_text(
                    f"CREATE INDEX {index_name} ON {table_name} ({column_name});"
                )
                await session.execute(create_index_sql)
                self.logger.info(f"Index created on {table_name}.{column_name}")
        return True