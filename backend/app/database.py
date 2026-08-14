from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
settings.app_data_path.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    settings.database_url,
    # timeout/pre_ping: 호스트 바인드 마운트(예: Docker Desktop gRPC-FUSE)의 일시적인
    # 잠금/끊김에도 커넥션을 재시도·재검증해 readonly 오류를 줄인다.
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
