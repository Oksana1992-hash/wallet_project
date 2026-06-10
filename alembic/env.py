import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 1. Добавляем корень проекта в пути поиска, чтобы Python видел модуль 'app'
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 2. Импортируем базовый класс и модели
from app.database import Base
import app.models  # Импорт обязателен, чтобы модели зарегистрировались в Base

config = context.config

# 3. Настройка логирования
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. Привязываем метаданные наших моделей к Alembic
target_metadata = Base.metadata

# 5. Динамически подменяем URL базы данных, если задана переменная окружения DATABASE_URL
if os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())
