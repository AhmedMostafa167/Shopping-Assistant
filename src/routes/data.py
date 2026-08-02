from fastapi import APIRouter, Depends, UploadFile, status, Request
from fastapi.responses import JSONResponse
from helpers.config import get_settings, Settings
from controllers import DataController, PreprocessingController, CategoryController, AssetController, EmbeddingsController
from models.db_schemes import Asset, Product
from models import AssetModel, CategoryModel, ProductModel
from models.enums import ResponseEnums, PreprocessingEnums
from .schemes.Process import ProcessRequest
import aiofiles
import logging
import os

logger = logging.getLogger('uvicorn')
data_router = APIRouter(
    prefix="/api/v1/data",
    tags=["api_v1"]
                        )

@data_router.post('/upload/{category_name}')
async def upload_data(request: Request,
                      category_name: str,
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
    category_model = await CategoryModel.create_instance(db_client=request.app.db_client)
    category_record = await category_model.get_category_or_create_one(category_name=category_name)
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    asset_record = Asset(
        asset_type=file.content_type,
        asset_name=file_path.split('/')[-1],
        asset_size=os.path.getsize(file_path),
        asset_category_name=category_name
        )
    
    stored_record = await asset_model.create_asset(asset=asset_record)

    
    logger.info(f"File Upload success: {stored_record}")

    return JSONResponse(
        status_code=status.HTTP_200_OK, 
        content={
                "message": ResponseEnums.FILE_UPLOAD_SUCESS.value,
                "asset_name": stored_record.asset_name,
                "category_name": category_record.category_name
                }
            )
    
@data_router.post('/validate/{asset_name}')
async def validate_data(request: Request,
                  asset_name: str,
                  app_settings: Settings = Depends(get_settings)):
    
    
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    asset_record = await asset_model.get_asset_by_name(asset_name=asset_name)
    if not asset_record :
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"message": ResponseEnums.ASSET_NOT_FOUND.value}
        )
    category_name, asset_name = asset_record.asset_category_name, asset_record.asset_name
    category_controller = CategoryController()
    category_path = category_controller.get_category_path(category_name)
    asset_path = AssetController.get_asset_path(asset_name=asset_name, category_path=category_path)
    
    preprocessing_controller = PreprocessingController(category_name=category_name)
    df = preprocessing_controller.load_into_dataframe(file_name=asset_path)
    signal, feedback = preprocessing_controller.validate_products(df, file_name=asset_path)

    if signal == PreprocessingEnums.DATA_VALIDATION_SUCCESS.value:
        logger.info(f"Data Validation Success!")
        return JSONResponse(
            status_code=status.HTTP_200_OK, 
            content={"message": signal, 
                     "asset_name": asset_name,
                    }       
            )
    elif signal == PreprocessingEnums.DATA_VALIDATION_DONE_WITH_ERRORS.value:
        logger.warning(f"Data Validation Done! but some rows aren't valid so will be deleted: {feedback}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                    "message": signal,                     
                    "feedback": feedback,
                    "asset_name": asset_name,
                    }
            )
    elif signal == PreprocessingEnums.DATA_VALIDATION_FAILED.value:
        logger.error(f"Data Validation Failed!: {feedback}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                    "message": signal,                     
                    "feedback": feedback,
                    "asset_name": asset_name,
                    }
            )

        
@data_router.post('/store/{asset_name}')
async def store_data(request: Request,
                    asset_name: str,
                    process_request: ProcessRequest,
                    app_settings: Settings = Depends(get_settings)
                  ):
    
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    asset_record = await asset_model.get_asset_by_name(asset_name=asset_name)
    if not asset_record :
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"message": ResponseEnums.ASSET_NOT_FOUND.value}
        )
    category_name, asset_name = asset_record.asset_category_name, asset_record.asset_name
    category_controller = CategoryController()
    category_path = category_controller.get_category_path(category_name)
    asset_path = AssetController.get_asset_path(asset_name=asset_name, category_path=category_path)
    
    preprocessing_controller = PreprocessingController(category_name=category_name)
    products_dict = preprocessing_controller.load_into_dataframe(file_name=asset_path).to_dict(orient="records")
    
    product_model = await ProductModel.create_instance(db_client=request.app.db_client)
    
    products = [
        Product(
            source_id=product["parent_asin"],
            title=product['title'],
            description=product['description'],
            store=product['store'],
            average_rating=product['average_rating'],
            rating_number=product['rating_number'],
            price=product['price'],
            image=product['image'],
            category_name=category_name,
            asset_id=asset_record[0].asset_id
        )
        for product in products_dict
    ]
    try:
        num_products_inserted = await product_model.insert_many_products(products, batch_size=process_request.batch_size)
    except Exception as e:
        logger.error(f"Error inserting products: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"message": ResponseEnums.PRODUCT_INSERTION_FAILED.value}
            )
        
    return JSONResponse(
            status_code=status.HTTP_200_OK, 
            content={
                    "message": ResponseEnums.PRODUCT_INSERTION_SUCCESS.value,
                    "num_products_inserted": num_products_inserted
                    }
            )
    
    
@data_router.post('/embed/{category_name}')
async def embed_data(request: Request,
                  category_name: str,
                  app_settings: Settings = Depends(get_settings)):
    
    product_model = await ProductModel.create_instance(db_client=request.app.db_client)
    products = await product_model.get_products_by_category(category_name=category_name, 
                                                            page_no=1, page_size=1300
                                                            )
    
    if len(products) == 0:
        logger.error("No Products in this category!")
    
    embeddings_controller = EmbeddingsController(
        vectordb_client=request.app.vectordb_client,
        embedding_client=request.app.embedding_client
    )
    
    status = await embeddings_controller.index_into_vectordb(category_name=category_name, products=products)
    
    if status: 
        logger.info("Vector indexing success!")
        return JSONResponse(
            status_code=status.HTTP_200_OK, 
            content={
                    "message": ResponseEnums.PRODUCT_INSERTION_SUCCESS.value,
                    "num_products_inserted": len(products)
                    }
            )
    
