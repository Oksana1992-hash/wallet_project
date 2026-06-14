import asyncio
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

# Импортируем приложение, фабрику сессий, get_db, engine и саму модель
from app.main import app
from app.database import AsyncSessionLocal, get_db, engine, Base
from app.models import Wallet


@pytest.fixture(scope="session")
def event_loop():
    """Создает один общий Event Loop для всех тестов в сессии.
    Это предотвращает ошибку 'attached to a different loop' в asyncpg.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db_dependency():
    """Фикстура автоматически создает таблицы перед каждым тестом,
    подменяет зависимость БД и изолирует сессии.
    """
    # 1. Создаем таблицы (если их еще нет) перед запуском теста
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Подменяем зависимость сессии в FastAPI
    async def _override_get_db():
        session = AsyncSessionLocal()
        try:
            yield session
        finally:
            await session.close()

    app.dependency_overrides[get_db] = _override_get_db

    yield

    # 3. Чистим переопределения и сбрасываем пул соединений
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def setup_wallet():
    """Фикстура создает в базе кошелек с балансом 1000.00 для тестов."""
    wallet_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        # Очищаем таблицу от старых записей
        await session.execute(
            text("TRUNCATE TABLE wallets RESTART IDENTITY CASCADE;")
        )

        wallet = Wallet(id=wallet_id, balance=1000.00)
        session.add(wallet)
        await session.commit()
    return wallet_id


@pytest.mark.asyncio
async def test_get_wallet_not_found():
    """Тест 1: Проверка возврата ошибки 404
    при запросе несуществующего кошелька."""
    fake_uuid = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"/api/v1/wallets/{fake_uuid}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Wallet not found"


@pytest.mark.asyncio
async def test_operation_wallet_not_found():
    """Тест 2: Проверка ошибки 404 при попытке выполнить операцию
    над несуществующим кошельком."""
    fake_uuid = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            f"/api/v1/wallets/{fake_uuid}/operation",
            json={"operation_type": "DEPOSIT", "amount": 100}
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Wallet not found"


@pytest.mark.asyncio
async def test_get_wallet_success(setup_wallet):
    """Тест 3: Проверяем успешное получение баланса существующего кошелька."""
    wallet_uuid = setup_wallet
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"/api/v1/wallets/{wallet_uuid}")
    assert response.status_code == 200
    assert float(response.json()["balance"]) == 1000.0


@pytest.mark.asyncio
async def test_deposit_operation_success(setup_wallet):
    """Тест 4: Проверяем успешное пополнение кошелька (DEPOSIT)."""
    wallet_uuid = setup_wallet
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            f"/api/v1/wallets/{wallet_uuid}/operation",
            json={"operation_type": "DEPOSIT", "amount": 500.00}
        )
    assert response.status_code == 200
    assert float(response.json()["balance"]) == 1500.0


@pytest.mark.asyncio
async def test_withdraw_operation_success(setup_wallet):
    """Тест 5: Проверяем успешное списание средств (WITHDRAW)."""
    wallet_uuid = setup_wallet
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            f"/api/v1/wallets/{wallet_uuid}/operation",
            json={"operation_type": "WITHDRAW", "amount": 300.00}
        )
    assert response.status_code == 200
    assert float(response.json()["balance"]) == 700.00


@pytest.mark.asyncio
async def test_withdraw_insufficient_funds(setup_wallet):
    """Тест 6: Проверяем ошибку 400, если денег на кошельке не хватает."""
    wallet_uuid = setup_wallet
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            f"/api/v1/wallets/{wallet_uuid}/operation",
            json={"operation_type": "WITHDRAW", "amount": 5000.00}
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient funds"


@pytest.mark.asyncio
async def test_concurrent_withdrawals(setup_wallet):
    """Тест 7: Обработка 10 параллельных запросов на списание средств."""
    wallet_uuid = setup_wallet

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # 10 человек одновременно списывают по 100 рублей через один клиент
        tasks = [
            ac.post(
                f"/api/v1/wallets/{wallet_uuid}/operation",
                json={"operation_type": "WITHDRAW", "amount": 100}
            )
            for _ in range(10)
        ]
        responses = await asyncio.gather(*tasks)

        # Проверяем, что все 10 запросов выстроились на уровне БД
        # и прошли успешно
        for r in responses:
            assert r.status_code == 200

        # Проверяем финальный баланс: 1000 - (10 * 100) должно быть ровно 0
        final_res = await ac.get(f"/api/v1/wallets/{wallet_uuid}")
        assert float(final_res.json()["balance"]) == 0.0
