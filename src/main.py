from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from urllib.parse import quote_plus

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent.graph import build_graph
from agent.memory_controller import MemoryController
from controllers import RetrievalController
from helpers.config import get_settings
from helpers.logging import configure_logging, get_logger
from models import MemoryModel, ProductModel, ProfileModel,ConversationModel
from models.enums import LogEventEnums
from routes import base, chat, data, conversations
from stores.llm.LLMProviderFactory import LLMProviderFactory
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(LogEventEnums.APPLICATION_STARTING.value)

    username = quote_plus(settings.POSTGRES_USERNAME)
    password = quote_plus(settings.POSTGRES_PASSWORD)
    host = settings.POSTGRES_HOST
    port = settings.POSTGRES_PORT
    database = quote_plus(settings.POSTGRES_DB)

    app.postgres_conn = (
        f"postgresql+asyncpg://{username}:{password}"
        f"@{host}:{port}/{database}"
    )

    app.langgraph_postgres_conn = (
        f"postgresql://{username}:{password}"
        f"@{host}:{port}/{database}"
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
    logger.info(
        LogEventEnums.VECTOR_STORE_CONNECTED.value,
        provider=settings.VECTOR_DB_BACKEND,
    )

    llm_factory = LLMProviderFactory(config=settings)

    app.embedding_client = llm_factory.create(
        provider=settings.LLM_BACKEND
    )

    app.embedding_client.set_embedding_model(
        model_id=settings.EMBEDDING_MODEL,
        embedding_size=settings.EMBEDDING_MODEL_SIZE,
    )

    app.llm_client = app.embedding_client
    app.llm_client.set_generation_model(
        model_id=settings.GENERATION_MODEL
    )

    app.product_model = await ProductModel.create_instance(
        db_client=app.db_client
    )

    app.profile_model = await ProfileModel.create_instance(
        db_client=app.db_client
    )

    app.memory_model = await MemoryModel.create_instance(
        db_client=app.db_client
    )
    app.conversation_model = await ConversationModel.create_instance(
        db_client=app.db_client
    )


    app.retrieval_controller = await RetrievalController.create_instance(
        embedding_client=app.embedding_client,
        vectordb_client=app.vectordb_client,
        db_client=app.db_client,
    )

    app.memory_controller = MemoryController(
        llm_provider=app.llm_client,
        memory_model=app.memory_model,
        profile_model=app.profile_model,
    )

    async with AsyncPostgresSaver.from_conn_string(
        app.langgraph_postgres_conn
    ) as checkpointer:
        await checkpointer.setup()

        app.checkpointer = checkpointer

        app.graph = build_graph(
            llm_provider=app.llm_client,
            retrieval_controller=app.retrieval_controller,
            product_model=app.product_model,
            memory_controller=app.memory_controller,
            checkpointer=app.checkpointer,
        )
        logger.info(LogEventEnums.APPLICATION_STARTED.value)

        try:
            yield
        finally:
            logger.info(LogEventEnums.APPLICATION_STOPPED.value)
            await app.vectordb_client.disconnect()
            await app.db_engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(base.base_router)
app.include_router(data.data_router)
app.include_router(chat.chat_router)
app.include_router(conversations.conversation_router)
