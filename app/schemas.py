from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from uuid import UUID
from decimal import Decimal


class OperationType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"


class WalletOperation(BaseModel):
    operation_type: OperationType
    # Сумма строго больше нуля и округлена до 2 знаков
    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        json_schema_extra={"type": "string", "example": "500.00"},
    )


class WalletResponse(BaseModel):
    id: UUID
    balance: Decimal = Field(
        ...,
        max_digits=12,
        decimal_places=2,
        json_schema_extra={"type": "string", "example": "1000.00"},
    )

    model_config = ConfigDict(from_attributes=True)
