from .BaseController import BaseController
from .CategoryController import CategoryController
from models.enums import AssetTypeEnums, PreprocessingEnums
from pydantic import BaseModel, ValidationError
import pandas as pd
import pyarrow.ipc as ipc
import os
import logging

class PreprocessingController(BaseController):
    def __init__(self, category_name: str):
        
        super().__init__()
        
        self.category_name = category_name
        self.category_controller = CategoryController()
        self.category_path = self.category_controller.get_category_path(self.category_name)
        
        
    def get_file_type(self, file_name: str):
        return os.path.splitext(file_name)[-1]
    
    def get_file_loader(self, file_name: str):
        file_type = self.get_file_type(file_name)
        logging.info(f"File Type: {file_type}")
        LOADERS = {
        AssetTypeEnums.CSV.value: pd.read_csv,
        AssetTypeEnums.EXCEL.value: pd.read_excel,
        AssetTypeEnums.JSON.value: pd.read_json,
        AssetTypeEnums.PARQUET.value: pd.read_parquet,
        AssetTypeEnums.ARROW.value: lambda f: ipc.open_file(f).read_all().to_pandas()
        }
        loader = LOADERS.get(file_type)
        return loader
    def load_into_dataframe(self, file_name: str):
        loader = self.get_file_loader(file_name)
        df = loader(file_name)
        return df
    
    def validate_products(self, df: pd.DataFrame):
        '''
        validate column names, data types, and values
        it should be like this:
            parent_asin: str
            title: str
            description: str
            filename: str
            store: str 
            average_rating: float
            rating_number: int
            price: float
            image: str
        '''
        records = df.to_dict(orient="records")

        valid_products = []
        feedback = []

        for i, row in enumerate(records):
            try:
                valid_products.append(Products.model_validate(row))
            except ValidationError as e:
                feedback.append({"row_index": i, "error": str(e)})
        if len(feedback) > 0:
            return PreprocessingEnums.DATA_VALIDATION_FAILED.value, feedback
        else:
            return PreprocessingEnums.DATA_VALIDATION_SUCCESS.value, feedback
        
        
        
class Products(BaseModel):
    parent_asin: str
    title: str = ''
    description: str = ''
    filename: str
    store: str = ''
    average_rating: float = 0
    rating_number: int = 0
    price: float = 0.0
    image: str = ''