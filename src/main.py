from fastapi import FastAPI
from routes import base, data
from helpers.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, async_session
from sqlalchemy.orm import sessionmaker

app = FastAPI()

# async def startup_span():
#     settings = get_settings()

#     app.postgres_conn = "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
#         settings.POSTGRES_USERNAME,
#         settings.POSTGRES_PASSWORD,
#         settings.POSTGRES_HOST,
#         settings.POSTGRES_PORT,
#         settings.POSTGRES_DB,
#     )
#     app.db_engine = create_async_engine(app.postgres_conn)
#     app.db_client = sessionmaker(
#         bind=app.db_engine, 
#         class_=async_session, 
#         expire_on_commit=False)


# async def shutdown_span():
#     app.db_engine.dispose()

app.include_router(base.base_router)
app.include_router(data.data_router)