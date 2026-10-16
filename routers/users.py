from fastapi import APIRouter,Depends,status,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from database import get_db
from models import User
from schemas import UserCreate,UserResponse

router=APIRouter(prefix="/users",tags=["Users"])

@router.post("",response_model=UserResponse,status_code=status.HTTP_201_CREATED)
def create_user(user_data:UserCreate,db:Session=Depends(get_db)):
    user=User(name=user_data.name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        if exc.orig.diag.constraint_name == "uq_users_normalized_name":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this name already exists.",
            ) from exc

        raise
    db.refresh(user)

    return user

@router.get("",response_model=list[UserResponse])
def list_users(db:Session=Depends(get_db)):
    statement=select(User).order_by(User.id)
    users=db.scalars(statement).all()
    return users
