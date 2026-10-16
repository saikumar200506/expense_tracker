from pydantic import BaseModel,ConfigDict,Field
from decimal import Decimal
from datetime import datetime

class UserCreate(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True)
    name:str=Field(min_length=1,max_length=100)

class UserResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int
    name:str

class GroupCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    created_by: int = Field(gt=0)

class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_by: int
    creator_name:str

class GroupMemberCreate(BaseModel):
    user_id: int = Field(gt=0)

class ExpenseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    paid_by: int = Field(gt=0)
    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
        allow_inf_nan=False,
    )
    description: str = Field(min_length=1)

class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    paid_by: int
    payer_name: str
    amount: Decimal
    description: str
    split_type: str
    created_at: datetime

class BalanceResponse(BaseModel):
    owes: dict[str, Decimal] = Field(default_factory=dict)

class UserSettlementResponse(BaseModel):
    pay: dict[str, Decimal] = Field(default_factory=dict)


class SettlementSuggestionsResponse(BaseModel):
    original_payment_count: int
    suggested_payment_count: int
    payments_saved: int
    suggestions: dict[str, UserSettlementResponse]

class SettlementMessageResponse(BaseModel):
    message: str