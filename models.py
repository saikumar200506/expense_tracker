from sqlalchemy import Index,text, String, func,ForeignKey,DateTime,Text,Numeric,CheckConstraint,ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from decimal import Decimal

from database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_normalized_name",
            text("lower(TRIM(BOTH FROM name))"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)




class Group(Base):
    __tablename__="groups"

    __table_args__ = (
        Index(
            "uq_groups_creator_normalized_name",
            "created_by",
            text("lower(TRIM(BOTH FROM name))"),
            unique=True,
        ),
    )
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(100),nullable=False)
    created_by:Mapped[int]=mapped_column(ForeignKey("users.id"),nullable=False)


class GroupMember(Base):
    __tablename__="group_members"
    group_id:Mapped[int]=mapped_column(ForeignKey("groups.id"),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),primary_key=True)

class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"),
        nullable=False,
    )

    paid_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    split_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="equal",
    )
    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_expenses_amount_positive",
        ),
        ForeignKeyConstraint(
            ["group_id", "paid_by"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_expenses_payer_membership",
        ),
        CheckConstraint(
            "split_type IN ('equal', 'custom')",
            name="ck_expenses_split_type",
        ),
    )

class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    __table_args__ = (
        CheckConstraint(
            "share_amount >= 0",
            name="ck_expense_splits_share_nonnegative",
        ),
    )

    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id"),
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        primary_key=True,
    )

    share_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )