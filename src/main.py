from contextlib import asynccontextmanager
from fastapi import FastAPI
from routes import base, data
from helpers.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from stores.llm.LLMProviderFactory import LLMProviderFactory
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
    vectordb_provider = VectorDBProviderFactory(config=settings, db_client=app.db_client)
    app.vectordb_client = vectordb_provider.create(provider=settings.VECTOR_DB_BACKEND)
    await app.vectordb_client.connect()
    llm_factory = LLMProviderFactory(config=settings)
    app.embedding_client = llm_factory.create(provider=settings.LLM_BACKEND)
    app.embedding_client.set_embedding_model(model_id=settings.EMBEDDING_MODEL, 
                                             embedding_size=settings.EMBEDDING_MODEL_SIZE)
    app.reranking_client = llm_factory.create(provider=settings.LLM_BACKEND)
    app.reranking_client.set_reranking_model(model_id=settings.RERANKING_MODEL)
    yield

    await app.db_engine.dispose()
    await app.vectordb_client.disconnect()

app = FastAPI(lifespan=lifespan)

app.include_router(base.base_router)
app.include_router(data.data_router)