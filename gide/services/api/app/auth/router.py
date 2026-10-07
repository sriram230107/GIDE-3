from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.auth.security import hash_password, make_token, verify_password
from app.core.database import get_db
from app.database.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Creds(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None


@router.post("/register")
async def register(c: Creds, db: AsyncSession = Depends(get_db)):
    email = c.email.strip().lower()
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "Email already registered")
    u = User(email=email, password_hash=hash_password(c.password), display_name=c.display_name)
    db.add(u)
    await db.commit()
    return {"token": make_token(str(u.id)), "user": {"id": str(u.id), "email": u.email, "display_name": u.display_name}}


@router.post("/login")
async def login(c: Creds, db: AsyncSession = Depends(get_db)):
    u = (await db.execute(select(User).where(User.email == c.email.strip().lower()))).scalar_one_or_none()
    if not u or not verify_password(c.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(str(u.id)), "user": {"id": str(u.id), "email": u.email, "display_name": u.display_name}}


@router.get("/me")
async def me(u: User = Depends(current_user)):
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name}
