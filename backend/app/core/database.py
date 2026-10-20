"""
数据库连接与会话管理
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from app.models.database import Base
from app.core.config import settings

# 创建引擎（SQLite 开发用，后续可换 PostgreSQL）
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite 需要
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """创建所有数据库表"""
    Base.metadata.create_all(bind=engine)
    # Additive migration for existing classroom databases; preserve projects and documents.
    columns = {column["name"] for column in inspect(engine).get_columns("projects")}
    if "style_skill_enabled" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE projects ADD COLUMN style_skill_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
    doc_columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    if "terminology_analysis" not in doc_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN terminology_analysis JSON"))


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
