from fastapi import APIRouter, Depends, UploadFile, status
from fastapi.responses import JSONResponse
from helpers.config import get_settings, Settings
from controllers import DataController, ProjectController
from models import ResponseEnums
import aiofiles
import os
import logging

logger = logging.getLogger('uvicorn-error')
data_router = APIRouter(
    prefix="/api/v1/data",
    tags=["api_v1"]
                        )

@data_router.post('/upload/{project_id}')
async def upload_data(project_id: str,
                      file: UploadFile,
                      app_settings: Settings = Depends(get_settings)):

    data_controller = DataController()
    
    is_valid, result_message = data_controller.validate_file(file)
    if not is_valid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"message": result_message}
            )   
 
    project_dir = ProjectController().get_project_path(project_id=project_id)
    file_path = data_controller.generate_unique_filename(file.filename, project_id=project_id)
    try:
        async with aiofiles.open(file_path, mode="wb") as f:
            while chunk:= await file.read(app_settings.FILE_DEFUALT_CHUNK_SIZE):
                await f.write(chunk)
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"message": ResponseEnums.FILE_UPLOAD_FAILED.value}
            )   
    
    return JSONResponse(
        status_code=status.HTTP_200_OK, 
        content={"message": ResponseEnums.FILE_UPLOAD_SUCESS.value}
        )
    
    
    