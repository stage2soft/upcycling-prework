from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_root_path: Path = Path("/data/root")
    selected_data_path: Path = Path("/data/selected")
    app_data_path: Path = Path("/app/data")
    host_data_root_path: str = ""
    host_selected_data_path: str = ""
    host_app_data_path: str = ""
    cors_origins: str = "http://localhost:18081,http://127.0.0.1:18081,http://localhost:18080,http://127.0.0.1:18080"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.app_data_path / 'prework.db'}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
