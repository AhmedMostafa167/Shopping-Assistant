from abc import ABC, abstractmethod
from typing import List
from models.db_schemes import RetrievedProduct

class VectorDBInterface(ABC):

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def is_table_existed(self, table_name: str) -> bool:
        pass

    @abstractmethod
    def list_all_tables(self) -> List:
        pass

    @abstractmethod
    def get_table_info(self, table_name: str) -> dict:
        pass

    @abstractmethod
    def delete_table(self, table_name: str):
        pass

    @abstractmethod
    def create_table(self, table_name: str, 
                                embedding_size: int,
                                do_reset: bool = False):
        pass

    @abstractmethod
    def insert_one(self, table_name: str, text: str, vector: list,
                         metadata: dict = None, 
                         record_id: str = None):
        pass

    @abstractmethod
    def insert_many(self, table_name: str, texts: list, 
                          vectors: list, metadata: list = None, 
                          record_ids: list = None, batch_size: int = 50):
        pass

    @abstractmethod
    def search_by_vector(self, table_name: str, vector: list, limit: int) -> List[RetrievedProduct]:
        pass
    