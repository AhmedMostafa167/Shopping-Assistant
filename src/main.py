from contextlib import asynccontextmanager
from fastapi import FastAPI
from routes import base, data
from helpers.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.postgres_conn = "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
        settings.POSTGRES_USERNAME,
        settings.POSTGRES_PASSWORD,
        settings.POSTGRES_HOST,
        settings.POSTGRES_PORT,
        settings.POSTGRES_DB,
    )
    app.db_engine = create_async_engine(app.postgres_conn)
    app.db_client = sessionmaker(
        bind=app.db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    yield

    await app.db_engine.dispose()

app = FastAPI(lifespan=lifespan)

app.include_router(base.base_router)
app.include_router(data.data_router)