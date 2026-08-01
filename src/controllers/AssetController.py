from .BaseController import BaseController
import os

class AssetController(BaseController):
    def __init__(self):
        super().__init__()
    
    @staticmethod
    def get_asset_path(asset_name: str, category_path: str):
        
        
        asset_path = os.path.join(
                    category_path,
                    asset_name
                    )
        return asset_path