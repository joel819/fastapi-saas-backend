from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, require_active_subscription
from app.models import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/me/premium")
def premium_feature(user: User = Depends(require_active_subscription)) -> dict:
    """Example endpoint gated behind an active paid subscription."""
    return {"message": f"Welcome to the {user.subscription.plan} plan, {user.email}."}
