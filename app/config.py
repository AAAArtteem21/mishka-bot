from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    groq_api_key: str = ""
    database_url: str = ""
    data_dir: str = "data"
    max_file_size_mb: int = 20
    groq_model: str = "openai/gpt-oss-20b"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def get_settings() -> Settings:
    return Settings()
