from contextlib import asynccontextmanager
import uuid
from fastapi import FastAPI, HTTPException, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .models import Wallet
from .schemas import WalletOperation, WalletResponse, OperationType
from fastapi.responses import HTMLResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Убрали создание таблиц через SQLAlchemy, теперь за это отвечает Alembic
    yield


app = FastAPI(title="Wallet API", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <title>Wallet API</title>
            <style>
                body { font-family: sans-serif; background: #f4f6f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                .card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; max-width: 400px; }
                h1 { color: #2c3e50; margin-bottom: 10px; }
                .status { display: inline-block; background: #2ecc71; color: white; padding: 5px 10px; border-radius: 20px; font-size: 14px; margin-bottom: 20px; }
                a { display: block; background: #3498db; color: white; text-decoration: none; padding: 12px; border-radius: 6px; font-weight: bold; transition: 0.2s; }
                a:hover { background: #2980b9; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Wallet REST API</h1>
                <div class="status">● Running</div>
                <p>Асинхронное веб-приложение для управления балансом кошельков успешно запущено.</p>
                <a href="/docs">Открыть Swagger UI Документацию</a>
            </div>
        </body>
    </html>
    """


@app.get("/api/v1/wallets/{wallet_uuid}", response_model=WalletResponse)
async def get_wallet(
        wallet_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Wallet).where(Wallet.id == wallet_uuid))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
        )
    return wallet


@app.post(
    "/api/v1/wallets/{wallet_uuid}/operation", response_model=WalletResponse
)
async def wallet_operation(
        wallet_uuid: uuid.UUID,
        operation: WalletOperation,
        db: AsyncSession = Depends(get_db)
):
    # Загружаем кошелек с блокировкой строки FOR UPDATE
    # для защиты от конкурентных запросов
    result = await db.execute(
        select(Wallet).where(Wallet.id == wallet_uuid).with_for_update()
    )
    wallet = result.scalar_one_or_none()

    # Если кошелька нет — возвращаем 404
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    # Выполняем математику изменения баланса
    if operation.operation_type == OperationType.WITHDRAW:
        if wallet.balance < operation.amount:
            raise HTTPException(status_code=400, detail="Insufficient funds")
        wallet.balance -= operation.amount
    elif operation.operation_type == OperationType.DEPOSIT:
        wallet.balance += operation.amount

    # Сохраняем изменения и фиксируем транзакцию, которая уже открыта
    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)

    # Возвращаем обновленный кошелек клиенту
    return wallet
