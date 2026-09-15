from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.graph import build_graph
from agent.memory_controller import MemoryController
from controllers import RetrievalController
from helpers.config import get_settings
from models import MemoryModel, ProductModel, ProfileModel
from routes import base, chat, data
from stores.llm.LLMProviderFactory import LLMProviderFactory
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    app.postgres_conn = (
        "postgresql+asyncpg://"
        f"{settings.POSTGRES_USERNAME}:{settings.POSTGRES_PASSWORD}@"
        f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/"
        f"{settings.POSTGRES_DB}"
    )
    app.db_engine = create_async_engine(
        app.postgres_conn,
        pool_pre_ping=True,
    )
    app.db_client = async_sessionmaker(
        bind=app.db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    vectordb_provider = VectorDBProviderFactory(
        config=settings,
        db_client=app.db_client,
    )
    app.vectordb_client = vectordb_provider.create(
        provider=settings.VECTOR_DB_BACKEND
    )
    await app.vectordb_client.connect()

    llm_factory = LLMProviderFactory(config=settings)
    app.embedding_client = llm_factory.create(provider=settings.LLM_BACKEND)
    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )
    app.llm_client = app.embedding_client
    app.llm_client.set_generation_model(model_id=settings.GENERATION_MODEL)

    # product_model = await ProductModel.create_instance(db_client=app.db_client)
    # profile_model = await ProfileModel.create_instance(db_client=app.db_client)
    # memory_model = await MemoryModel.create_instance(db_client=app.db_client)
    # retrieval_controller = await RetrievalController.create_instance(
    #     embedding_client=app.embedding_client,
    #     vectordb_client=app.vectordb_client,
    #     db_client=app.db_client,
    # )
    # memory_controller = MemoryController(
    #     llm_provider=app.llm_client,
    #     memory_model=memory_model,
    #     profile_model=profile_model,
    # )

    # The saver owns an async Psycopg connection. Keep its context open for
    # every graph invocation and close it during application shutdown.
    # from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    # async with AsyncPostgresSaver.from_conn_string(
    #     settings.LANGGRAPH_CHECKPOINT_DATABASE_URL
    # ) as checkpointer:
    #     app.checkpointer = checkpointer
    #     app.graph = build_graph(
    #         llm_provider=app.llm_client,
    #         retrieval_controller=retrieval_controller,
    #         product_model=product_model,
    #         memory_controller=memory_controller,
    #         checkpointer=checkpointer,
    #     )
    #     try:
    yield
        # finally:
    await app.vectordb_client.disconnect()
    await app.db_engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(base.base_router)
app.include_router(data.data_router)
app.include_router(chat.chat_router)
