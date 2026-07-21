from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    
    APP_NAME: str
    APP_VERSION: str
    FILE_ALLOWED_TYPES: list
    FILE_ALLOWED_SIZE: int
    FILE_DEFUALT_CHUNK_SIZE: int
    POSTGRES_USERNAME: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_MAIN_DATABASE: str
    
    class Config:
        env_file = ".env"
        
    
def get_settings():
    return Settings()
        