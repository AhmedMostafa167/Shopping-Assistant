from .BaseController import BaseController
from .ProjectController import ProjectController
from fastapi import UploadFile
from models import ResponseEnums   
import re 
import os
class DataController(BaseController):
    def __init__(self):
        super().__init__()
        self.SIZE_SCALE: int = 1048576 # convert MB to bytes
        
    def validate_file(self, file: UploadFile):
        if file.content_type not in self.app_settings.FILE_ALLOWED_TYPES:
            return False, ResponseEnums.FILE_TYPE_NOT_SUPPORTED.value

        if file.size > self.app_settings.FILE_ALLOWED_SIZE*self.SIZE_SCALE:
            return False, ResponseEnums.FILE_SIZE_EXCEEDED.value
        
        return True, ResponseEnums.FILE_VALIDATION_SUCESS.value
    def generate_unique_filename(self, orig_filename: str, project_id: str) -> str:
        
        random_string = self.generate_random_string()
        project_controller = ProjectController()
        project_path = project_controller.get_project_path(project_id)
        
        cleaned_filename = self.get_clean_filename(orig_filename)
        
        new_file_path = os.path.join(
            project_path,
            random_string+'_'+cleaned_filename
            )
        while os.path.exists(new_file_path):
            random_string = self.generate_random_string()
            new_file_path = os.path.join(
                project_path,
                random_string, 
                '_',
                cleaned_filename
                )
            
        return new_file_path
        
    def get_clean_filename(self, filename: str) -> str:
        return re.sub(r"[^\w.]", '', filename)
        