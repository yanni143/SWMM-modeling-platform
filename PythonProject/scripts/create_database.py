import argparse
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from config import get_settings


VALID_DATABASE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def create_database(database_name: str) -> bool:
    if not VALID_DATABASE_NAME.fullmatch(database_name):
        raise ValueError("数据库名只能包含字母、数字和下划线，且必须以字母开头")

    settings = get_settings()
    configured_url = make_url(settings.database_url)
    admin_database = "postgres" if configured_url.get_backend_name() == "postgresql" else None
    if not admin_database:
        raise ValueError("当前仅支持自动创建 PostgreSQL 数据库")

    admin_url = configured_url.set(database=admin_database)
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": database_name},
            ).scalar()
            if exists:
                return False
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            return True
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the SWMM platform PostgreSQL database")
    parser.add_argument("--name", default=get_settings().database_name)
    args = parser.parse_args()
    created = create_database(args.name)
    print(f'数据库 "{args.name}" ' + ("创建完成" if created else "已存在"))


if __name__ == "__main__":
    main()
