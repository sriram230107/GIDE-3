from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_token
from app.core.database import get_db
from app.database.models import User

bearer = HTTPBearer(auto_error=False)


async def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer), db: AsyncSession = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(401, "Not authenticated")
    try:
        uid = UUID(decode_token(cred.credentials))
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    user = await db.get(User, uid)
    if user is None:
        raise HTTPException(401, "User no longer exists")
    return user
