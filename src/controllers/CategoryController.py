from .BaseController import BaseController
from models.enums import ResponseEnums
import os
class CategoryController(BaseController):
    def __init__(self):
        super().__init__()
        
    @staticmethod
    def get_category_path(self, category_name: str):
                
        category_dir = os.path.join(
            self.files_dir,
            category_name.lower()
            )
        
        if not os.path.exists(category_dir):
            os.makedirs(category_dir)
        
        return category_dir