import asyncio
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

# Импортируем приложение, фабрику сессий, get_db и саму модель кошелька
from app.main import app
from app.database import AsyncSessionLocal, get_db, engine
from app.models import Base, Wallet


@pytest.fixture(scope="function", autouse=True)
async def init_test_database():
    """Фикстура уровня функции. Автоматически создает и чистит таблицы."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function", autouse=True)
async def setup_db_dependency():
    """Фикстура изолирует сессии для каждого теста."""
    async def _override_get_db():
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def client():
    """Единая фикстура для HTTP-клиента. Решает проблемы с lifespan."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture(scope="function")
async def setup_wallet():
    """Фикстура создает кошелек для теста."""
    wallet_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        wallet = Wallet(id=wallet_id, balance=1000.00)
        session.add(wallet)
        await session.commit()
    return wallet_id


@pytest.mark.asyncio
async def test_get_wallet_not_found(client):
    """Тест 1: Проверка возврата ошибки 404
    при запросе несуществующего кошелька."""
    fake_uuid = uuid.uuid4()
    response = await client.get(f"/api/v1/wallets/{fake_uuid}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Wallet not found"


@pytest.mark.asyncio
async def test_operation_wallet_not_found(client):
    """Тест 2: Проверка ошибки 404 при попытке выполнить операцию
    над несуществующим кошельком."""
    fake_uuid = uuid.uuid4()
    response = await client.post(
        f"/api/v1/wallets/{fake_uuid}/operation",
        json={"operation_type": "DEPOSIT", "amount": 100},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Wallet not found"


@pytest.mark.asyncio
async def test_get_wallet_success(client, setup_wallet):
    """Тест 3: Проверяем успешное получение баланса существующего кошелька."""
    wallet_uuid = setup_wallet
    response = await client.get(f"/api/v1/wallets/{wallet_uuid}")
    assert response.status_code == 200
    assert float(response.json()["balance"]) == 1000.0


@pytest.mark.asyncio
async def test_deposit_operation_success(client, setup_wallet):
    """Тест 4: Проверяем успешное пополнение кошелька (DEPOSIT)."""
    wallet_uuid = setup_wallet
    response = await client.post(
        f"/api/v1/wallets/{wallet_uuid}/operation",
        json={"operation_type": "DEPOSIT", "amount": 500.00},
    )
    assert response.status_code == 200
    assert float(response.json()["balance"]) == 1500.0


@pytest.mark.asyncio
async def test_withdraw_operation_success(client, setup_wallet):
    """Тест 5: Проверяем успешное списание средств (WITHDRAW)."""
    wallet_uuid = setup_wallet
    response = await client.post(
        f"/api/v1/wallets/{wallet_uuid}/operation",
        json={"operation_type": "WITHDRAW", "amount": 300.00},
    )
    assert response.status_code == 200
    assert float(response.json()["balance"]) == 700.00


@pytest.mark.asyncio
async def test_withdraw_insufficient_funds(client, setup_wallet):
    """Тест 6: Проверяем ошибку 400, если денег на кошельке не хватает."""
    wallet_uuid = setup_wallet
    response = await client.post(
        f"/api/v1/wallets/{wallet_uuid}/operation",
        json={"operation_type": "WITHDRAW", "amount": 5000.00},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient funds"


@pytest.mark.asyncio
async def test_concurrent_withdrawals(setup_wallet):
    """Тест 7: Обработка 10 параллельных запросов на списание средств."""
    wallet_uuid = setup_wallet

    # Независимый клиент для изоляции параллельных потоков в Docker
    async def make_single_request():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac_isolated:
            return await ac_isolated.post(
                f"/api/v1/wallets/{wallet_uuid}/operation",
                json={"operation_type": "WITHDRAW", "amount": 100},
            )

    # 10 человек одновременно списывают по 100 рублей
    tasks = [make_single_request() for _ in range(10)]
    responses = await asyncio.gather(*tasks)

    # Проверяем, что все 10 запросов выстроились и прошли успешно
    for r in responses:
        assert r.status_code == 200

    # Проверяем финальный баланс: 1000 - (10 * 100) должно быть ровно 0
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        final_res = await ac.get(f"/api/v1/wallets/{wallet_uuid}")
    assert float(final_res.json()["balance"]) == 0.0
