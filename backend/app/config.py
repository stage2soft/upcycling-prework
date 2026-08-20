from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_root_path: Path = Path("/data/root")
    thumbnail_root_path: Path | None = Field(
        default=None,
    )
    selected_data_path: Path = Path("/data/selected")
    app_data_path: Path = Path("/app/data")
    host_data_root_path: str = ""
    host_thumbnail_root_path: str = ""
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

    @property
    def thumbnail_enabled(self) -> bool:
        if not self.thumbnail_root_path:
            return False
        data_path = Path(self.host_data_root_path) if self.host_data_root_path else self.data_root_path
        thumbnail_path = Path(self.host_thumbnail_root_path) if self.host_thumbnail_root_path else self.thumbnail_root_path
        return data_path.resolve() != thumbnail_path.resolve()

    @property
    def thumbnail_error(self) -> str:
        if not self.thumbnail_root_path:
            return "THUMBNAIL_ROOT_PATH가 설정되지 않았습니다."
        data_path = Path(self.host_data_root_path) if self.host_data_root_path else self.data_root_path
        thumbnail_path = Path(self.host_thumbnail_root_path) if self.host_thumbnail_root_path else self.thumbnail_root_path
        if data_path.resolve() == thumbnail_path.resolve():
            return "THUMBNAIL_ROOT_PATH와 DATA_ROOT_PATH는 서로 다른 경로여야 합니다."
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
