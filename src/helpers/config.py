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
    CO_API_KEY: str
    FILE_DEFAULT_CHUNK_SIZE: int = 512000
    class Config:
        env_file = ".env"
        
    
def get_settings():
    return Settings()
        