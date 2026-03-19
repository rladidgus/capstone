from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    database_url: str = ""

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_index_name: str = "viewpoint-memos"
    pinecone_environment: str = "us-east-1"

    # Public APIs
    openweather_api_key: str = ""
    bok_api_key: str = ""        # 한국은행 ECOS
    seoul_api_key: str = ""      # 서울 열린데이터광장

    # App
    upload_dir: str = "data/uploads"
    max_retry_count: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
