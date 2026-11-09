import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database.connection import get_db
from database.config import settings
from database.models import User

bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310_000)
    return 'pbkdf2_sha256$310000$' + salt.hex() + '$' + derived.hex()

def check_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, digest = stored.split('$')
        if scheme != 'pbkdf2_sha256': return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False

def create_token(user: User) -> str:
    if len(settings().jwt_secret) < 32:
        raise RuntimeError('Set JWT_SECRET to a random secret of at least 32 characters')
    return jwt.encode({'sub': str(user.id), 'role': user.role, 'exp': datetime.now(timezone.utc) + timedelta(hours=8)}, settings().jwt_secret, algorithm='HS256')

def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds: raise HTTPException(401, 'Authentication required')
    try:
        payload = jwt.decode(creds.credentials, settings().jwt_secret, algorithms=['HS256'])
        uid = int(payload['sub'])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, 'Invalid token')
    user = db.get(User, uid)
    if not user or not user.is_active: raise HTTPException(401, 'User not active')
    return user

def optional_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User | None:
    if not creds: return None
    return current_user(creds, db)
