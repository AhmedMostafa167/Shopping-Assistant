from pathlib import Path
import os
import sys


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

# Imports of the application controllers construct settings objects.  Tests use
# fakes for all external services, so provide harmless values for required
# settings instead of depending on a developer's .env file.
TEST_SETTINGS = {
    "APP_NAME": "test",
    "APP_VERSION": "test",
    "FILE_ALLOWED_TYPES": "[]",
    "FILE_ALLOWED_SIZE": "1",
    "POSTGRES_USERNAME": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_DB": "test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_MAIN_DATABASE": "test",
    "EMBEDDING_MODEL_SIZE": "3",
    "EMBEDDING_MODEL": "test",
    "VECTOR_DB_BACKEND": "test",
    "LLM_BACKEND": "test",
    "COHERE_API_KEY": "test",
    "GENERATION_MODEL": "test",
    "DEFAULT_INPUT_MAX_CHARACTERS": "1000",
    "DEFAULT_GENERATION_MAX_OUTPUT_TOKENS": "100",
    "DEFAULT_GENERATION_TEMPERATURE": "0",
    "RERANKING_MODEL": "test",
}

for key, value in TEST_SETTINGS.items():
    os.environ.setdefault(key, value)
