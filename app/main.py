from contextlib import asynccontextmanager
import uuid
from fastapi import FastAPI, HTTPException, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .database import engine, Base, get_db
from .models import Wallet
from .schemas import WalletOperation, WalletResponse, OperationType


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Wallet API", lifespan=lifespan)


@app.get("/api/v1/wallets/{wallet_uuid}", response_model=WalletResponse)
async def get_wallet(wallet_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Wallet).where(Wallet.id == wallet_uuid))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    return wallet


@app.post("/api/v1/wallets/{wallet_uuid}/operation", response_model=WalletResponse)
async def wallet_operation(wallet_uuid: uuid.UUID, operation: WalletOperation, db: AsyncSession = Depends(get_db)):
    # Начинаем явную транзакцию
    async with db.begin():
        result = await db.execute(
            select(Wallet).where(Wallet.id == wallet_uuid).with_for_update()
        )
        wallet = result.scalar_one_or_none()

        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        if operation.operation_type == OperationType.WITHDRAW:
            if wallet.balance < operation.amount:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")
            wallet.balance -= operation.amount
        elif operation.operation_type == OperationType.DEPOSIT:
            wallet.balance += operation.amount

        db.add(wallet)

    await db.refresh(wallet)
    return wallet
