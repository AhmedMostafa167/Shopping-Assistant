from fastapi import APIRouter, Depends, UploadFile, status
from fastapi.responses import JSONResponse
from helpers.config import get_settings, Settings
from controllers import DataController, PreprocessingController
from models.enums import ResponseEnums
import aiofiles
import logging

logger = logging.getLogger('uvicorn')
data_router = APIRouter(
    prefix="/api/v1/data",
    tags=["api_v1"]
                        )

@data_router.post('/upload/{category_name}')
async def upload_data(category_name: str,
                      file: UploadFile,
                      app_settings: Settings = Depends(get_settings)):

    data_controller = DataController()
    
    is_valid, result_message = data_controller.validate_file(file)
    if not is_valid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"message": result_message}
            )   
 
    file_path = data_controller.generate_unique_filename(file.filename, category_name=category_name)
    try:
        async with aiofiles.open(file_path, mode="wb") as f:
            while chunk:= await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                await f.write(chunk)
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"message": ResponseEnums.FILE_UPLOAD_FAILED.value}
            )   
    logging.info(f"File uploaded!\nValidating Column Names, Data Types, and Values...")
    preprocessing_controller = PreprocessingController(category_name=category_name)
    df = preprocessing_controller.load_into_dataframe(file_name=file_path)
    signal, feedback = preprocessing_controller.validate_products(df)
    if len(feedback)==0:
        logging.info(f"Data Validation Success!")
        return JSONResponse(
            status_code=status.HTTP_200_OK, 
            content={"message": ResponseEnums.FILE_UPLOAD_SUCESS.value}
            )
    else:
        logging.info(f"Data Validation Failed!: {feedback}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"message": ResponseEnums.FILE_UPLOAD_FAILED.value, "feedback": feedback}
            )
    

