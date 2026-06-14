import uuid
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Numeric
from .database import Base


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
