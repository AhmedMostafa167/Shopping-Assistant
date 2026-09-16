from fastapi import APIRouter, Depends, UploadFile, status, Request
from fastapi.responses import JSONResponse
from helpers.config import get_settings, Settings
from helpers.logging import get_logger
from controllers import DataController, PreprocessingController, CategoryController, AssetController, EmbeddingsController, RetrievalController
from models.db_schemes import Asset, Product
from models import AssetModel, CategoryModel, ProductModel
from models.enums import ResponseEnums, PreprocessingEnums, LogEventEnums, MessageEnums
from .schemas.Process import ProcessRequest
import aiofiles
import os

logger = get_logger(__name__)
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
        logger.exception(LogEventEnums.FILE_UPLOAD_FAILED.value, error=str(e), filename=file.filename)
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

    
    logger.info(
        LogEventEnums.FILE_UPLOAD_COMPLETED.value,
        asset_name=stored_record.asset_name,
        category_name=category_name,
    )

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
        logger.info(LogEventEnums.DATA_VALIDATION_COMPLETED.value, signal=signal, asset_name=asset_name)
        return JSONResponse(
            status_code=status.HTTP_200_OK, 
            content={"message": signal, 
                     "asset_name": asset_name,
                    }       
            )
    elif signal == PreprocessingEnums.DATA_VALIDATION_DONE_WITH_ERRORS.value:
        logger.warning(
            LogEventEnums.DATA_VALIDATION_COMPLETED.value,
            signal=signal,
            feedback=feedback,
            asset_name=asset_name,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                    "message": signal,                     
                    "feedback": feedback,
                    "asset_name": asset_name,
                    }
            )
    elif signal == PreprocessingEnums.DATA_VALIDATION_FAILED.value:
        logger.error(
            LogEventEnums.DATA_VALIDATION_COMPLETED.value,
            signal=signal,
            feedback=feedback,
            asset_name=asset_name,
        )
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
        logger.exception(
            LogEventEnums.PRODUCT_INSERTION_FAILED.value,
            error=str(e),
            category_name=category_name,
        )
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
        logger.warning(MessageEnums.NO_PRODUCTS_FOUND.value, category_name=category_name)
    
    embeddings_controller = EmbeddingsController(
        vectordb_client=request.app.vectordb_client,
        embedding_client=request.app.embedding_client
    )
    
    result = await embeddings_controller.index_into_vectordb(category_name=category_name, products=products)
    
    if result: 
        logger.info(
            LogEventEnums.VECTOR_INDEXING_COMPLETED.value,
            category_name=category_name,
            product_count=len(products),
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, 
            content={
                    "message": ResponseEnums.PRODUCT_INSERTION_SUCCESS.value,
                    "num_products_inserted": len(products)
                    }
            )
    
@data_router.post('/retrieve/{category_name}')
async def retrieve_products(request: Request,
                    category_name: str,
                    query: str,
                    app_settings: Settings = Depends(get_settings)):
    
    retrieval_controller = RetrievalController(embedding_client=request.app.embedding_client,
                                               vectordb_client=request.app.vectordb_client,
                                               reranking_client=request.app.reranking_client,
                                               db_client=request.app.db_client
                                               )
    embeddings_controller = EmbeddingsController(
        vectordb_client=request.app.vectordb_client,
        embedding_client=request.app.embedding_client
    )
    kw_resuilts = await retrieval_controller.keyword_search(query=query, top_k=10)
    vector_results = await retrieval_controller.vector_search(texts=[query], top_k=10, category_name=category_name)
    fused_results = retrieval_controller.fuse_results(vector_results, kw_resuilts, k=60)
    reranked_results = await retrieval_controller.rerank_results(fused_results, query)
    
    if len(reranked_results) == 0:
        return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST, 
                content={
                        "message": ResponseEnums.PRODUCT_RETRIEVAL_FAILED.value,
                        }
                )
    
    return JSONResponse(
            status_code=status.HTTP_200_OK, 
            content={
                    "message": ResponseEnums.PRODUCT_RETRIEVAL_SUCCESS.value,
                    "num_products_retrieved": len(reranked_results),
                    "products": [product.model_dump(allow_nan=True) for product in reranked_results]
                    }
            )
