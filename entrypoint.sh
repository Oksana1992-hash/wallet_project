#!/bin/sh
set -e

echo "Applying database migrations via Alembic..."
alembic upgrade head

echo "Ensuring all tables exist via SQLAlchemy..."
python -c "
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from app.database import Base
import app.models

async def init_db():
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        engine = create_async_engine(db_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

asyncio.run(init_db())
"

echo "Starting Uvicorn server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
