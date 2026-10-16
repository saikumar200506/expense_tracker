from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import get_db
from typing import Union
from services import calculate_balances,calculate_net_balances,suggest_settlements
from models import Group, GroupMember, User,Expense,ExpenseSplit
from schemas import GroupCreate, GroupResponse,GroupMemberCreate,UserResponse,BalanceResponse
from schemas import SettlementMessageResponse,SettlementSuggestionsResponse,UserSettlementResponse

router = APIRouter(prefix="/groups", tags=["Groups"])

@router.post(
    "",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_group(
    group_data: GroupCreate,
    db: Session = Depends(get_db),
):
    creator = db.get(User, group_data.created_by)

    if creator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator user not found.",
        )

    group = Group(
        name=group_data.name,
        created_by=group_data.created_by,
    )
    db.add(group)

    try:
        db.flush()

        membership = GroupMember(
            group_id=group.id,
            user_id=creator.id,
        )
        db.add(membership)

        db.commit()
    except IntegrityError as exc:
        db.rollback()

        if exc.orig.diag.constraint_name == "uq_groups_creator_normalized_name":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A group with this name already exists for this creator.",
            ) from exc
        raise

    db.refresh(group)
    return GroupResponse(
        id=group.id,
        name=group.name,
        created_by=group.created_by,
        creator_name=creator.name,
    )

@router.get("", response_model=list[GroupResponse])
def list_groups(db: Session = Depends(get_db)):
    statement = (
        select(
            Group.id,
            Group.name,
            Group.created_by,
            User.name.label("creator_name"),
        )
        .join(User, Group.created_by == User.id)
        .order_by(Group.id)
    )

    return db.execute(statement).mappings().all()

@router.post(
    "/{group_id}/members",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_group_member(
    group_id: int,
    member_data: GroupMemberCreate,
    db: Session = Depends(get_db),
):
    group = db.get(Group, group_id)

    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found.",
        )

    user = db.get(User, member_data.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    membership = GroupMember(
        group_id=group.id,
        user_id=user.id,
    )
    db.add(membership)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        if exc.orig.diag.constraint_name == "group_members_pkey":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this group.",
            ) from exc
        raise

    db.refresh(user)
    return user

@router.get(
    "/{group_id}/members",
    response_model=list[UserResponse],
)
def list_group_members(
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
        select(User)
        .join(GroupMember, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
        .order_by(User.id)
    )

    return db.scalars(statement).all()

@router.get(
    "/{group_id}/balances",
    response_model=dict[str, BalanceResponse],
)
def get_group_balances(
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
            Expense.paid_by,
            ExpenseSplit.user_id,
            ExpenseSplit.share_amount,
        )
        .join(ExpenseSplit, ExpenseSplit.expense_id == Expense.id)
        .where(Expense.group_id == group_id)
    )

    expense_shares = [
        (payer_id, member_id, share_amount)
        for payer_id, member_id, share_amount
        in db.execute(statement)
    ]

    balances = calculate_balances(expense_shares)

    members_statement = (
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .order_by(User.id)
    )
    members = db.scalars(members_statement).all()

    names = {member.id: member.name for member in members}
    response = {
        member.name: BalanceResponse()
        for member in members
    }

    for (debtor_id, creditor_id), amount in sorted(balances.items()):
        debtor_name = names[debtor_id]
        creditor_name = names[creditor_id]
        response[debtor_name].owes[creditor_name] = amount

    return response

@router.get(
    "/{group_id}/settlement-suggestions",
    response_model=Union[
        SettlementSuggestionsResponse,
        SettlementMessageResponse,
    ],
)
def get_settlement_suggestions(
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
            Expense.paid_by,
            ExpenseSplit.user_id,
            ExpenseSplit.share_amount,
        )
        .join(ExpenseSplit, ExpenseSplit.expense_id == Expense.id)
        .where(Expense.group_id == group_id)
    )

    expense_shares = [
        (payer_id, member_id, share_amount)
        for payer_id, member_id, share_amount
        in db.execute(statement)
    ]

    members_statement = (
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .order_by(User.id)
    )
    members = db.scalars(members_statement).all()
    member_ids = [member.id for member in members]

    pair_balances = calculate_balances(expense_shares)
    net_balances = calculate_net_balances(pair_balances, member_ids)
    candidate_plan = suggest_settlements(net_balances)

    original_count = len(pair_balances)
    suggested_count = len(candidate_plan)

    if suggested_count >= original_count:
        return SettlementMessageResponse(
            message="No meaningful settlement suggestions found."
        )

    names = {member.id: member.name for member in members}
    suggestions = {
        member.name: UserSettlementResponse()
        for member in members
    }

    for (debtor_id, creditor_id), amount in sorted(candidate_plan.items()):
        debtor_name = names[debtor_id]
        creditor_name = names[creditor_id]
        suggestions[debtor_name].pay[creditor_name] = amount

    return SettlementSuggestionsResponse(
        original_payment_count=original_count,
        suggested_payment_count=suggested_count,
        payments_saved=original_count - suggested_count,
        suggestions=suggestions,
    )