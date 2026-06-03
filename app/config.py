"""Application configuration, loaded from the .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    max_results: int = 20
    headless: bool = True
    enrich_websites: bool = True
    scrape_timeout_ms: int = 45000


settings = Settings()
