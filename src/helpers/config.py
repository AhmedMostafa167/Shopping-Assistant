from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    
    APP_NAME: str
    APP_VERSION: str
    FILE_ALLOWED_TYPES: list
    FILE_ALLOWED_SIZE: int
    POSTGRES_USERNAME: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_MAIN_DATABASE: str
    EMBEDDING_MODEL_SIZE: int
    EMBEDDING_MODEL: str
    VECTOR_DB_BACKEND: str
    FILE_DEFAULT_CHUNK_SIZE: int = 512000
    LLM_BACKEND: str
    GENERATION_BACKEND: str = "COHERE"
    COHERE_API_KEY: str
    GROQ_API_KEY: str = ""
    GENERATION_MODEL: str
    DEFAULT_INPUT_MAX_CHARACTERS: int
    DEFAULT_GENERATION_MAX_OUTPUT_TOKENS: int
    DEFAULT_GENERATION_TEMPERATURE: float
    EMBEDDING_MODEL_SIZE: int
    RERANKING_MODEL: str

    LANGFUSE_TRACING_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_TRACING_ENVIRONMENT: str = "development"
    # Which prompt versions the app serves. Evaluation sets "staging" to test a candidate.
    LANGFUSE_PROMPT_LABEL: str = "production"

    @property
    def langfuse_configured(self) -> bool:
        """True when Langfuse can be reached at all (prompts work even with tracing off)."""
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)

    @model_validator(mode="after")
    def check_langfuse_keys(self):
        if self.LANGFUSE_TRACING_ENABLED and not self.langfuse_configured:
            raise ValueError(
                "LANGFUSE_TRACING_ENABLED is true but LANGFUSE_PUBLIC_KEY or "
                "LANGFUSE_SECRET_KEY is empty"
            )
        return self

    class Config(SettingsConfigDict):
        env_file = ".env"
        
    
def get_settings():
    return Settings()
