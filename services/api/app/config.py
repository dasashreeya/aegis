from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AEGIS_", env_file=".env", extra="ignore")

    environment: str = "development"
    storage_backend: Literal["memory", "firestore"] = "memory"
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    pubsub_topic: str = "aegis-decisions"
    model_armor_template: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

