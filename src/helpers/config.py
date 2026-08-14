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
    COHERE_API_KEY: str
    GENERATION_MODEL: str
    DEFAULT_INPUT_MAX_CHARACTERS: int
    DEFAULT_GENERATION_MAX_OUTPUT_TOKENS: int
    DEFAULT_GENERATION_TEMPERATURE: float
    EMBEDDING_MODEL_SIZE: int
    RERANKING_MODEL: str
    
    class Config:
        env_file = ".env"
        
    
def get_settings():
    return Settings()
