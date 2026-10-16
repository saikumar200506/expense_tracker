from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from services import calculate_equal_shares
from sqlalchemy.orm import Session

from database import get_db
from models import Expense, ExpenseSplit, Group, GroupMember, User
from schemas import ExpenseCreate, ExpenseResponse

router = APIRouter(
    prefix="/groups/{group_id}/expenses",
    tags=["Expenses"],
)
@router.post(
    "",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_expense(
    group_id: int,
    expense_data: ExpenseCreate,
    db: Session = Depends(get_db),
):
    group = db.get(Group, group_id)

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found.",
        )

    payer = db.get(User, expense_data.paid_by)

    if payer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payer user not found.",
        )

    statement = select(GroupMember.user_id).where(
        GroupMember.group_id == group_id
    )
    member_ids = list(db.scalars(statement))

    if payer.id not in member_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payer must be a member of this group.",
        )

    shares = calculate_equal_shares(
        expense_data.amount,
        member_ids,
    )

    expense = Expense(
        group_id=group.id,
        paid_by=payer.id,
        amount=expense_data.amount,
        description=expense_data.description,
        split_type="equal",
    )

    try:
        db.add(expense)
        db.flush()

        for user_id, share_amount in shares.items():
            split = ExpenseSplit(
                expense_id=expense.id,
                user_id=user_id,
                share_amount=share_amount,
            )
            db.add(split)

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    db.refresh(expense)

    return ExpenseResponse(
        id=expense.id,
        group_id=expense.group_id,
        paid_by=expense.paid_by,
        payer_name=payer.name,
        amount=expense.amount,
        description=expense.description,
        split_type=expense.split_type,
        created_at=expense.created_at,
    )

@router.get("", response_model=list[ExpenseResponse])
def list_group_expenses(
    group_id: int,
    db: Session = Depends(get_db),
):
    group = db.get(Group, group_id)

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found.",
        )

    statement = (
        select(
            Expense.id,
            Expense.group_id,
            Expense.paid_by,
            User.name.label("payer_name"),
            Expense.amount,
            Expense.description,
            Expense.split_type,
            Expense.created_at,
        )
        .join(User, Expense.paid_by == User.id)
        .where(Expense.group_id == group_id)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
    )

    return db.execute(statement).mappings().all()