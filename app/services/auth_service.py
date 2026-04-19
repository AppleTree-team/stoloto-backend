import hashlib
from datetime import datetime, timedelta

from jose import jwt, JWTError

from app.db.db import fetch


# --------------------
# CONFIG
# --------------------
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


# --------------------
# HASH PASSWORD
# --------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# --------------------
# CREATE JWT
# --------------------
def create_session_token(user_id: int, username: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# --------------------
# DECODE JWT
# --------------------
def decode_session_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# --------------------
# LOGIN (ONLY HERE CREATES TOKEN)
# --------------------
def login(username: str, password: str):
    user = fetch(
        "SELECT * FROM users WHERE username = %s",
        (username,)
    )

    if not user:
        return None

    if user["password"] != hash_password(password):
        return None

    token = create_session_token(
        user_id=user["id"],
        username=user["username"]
    )

    return {
        "user_id": user["id"],
        "username": user["username"],
        "token": token
    }


# --------------------
# GET USER FROM DB
# --------------------
def get_user_by_id(user_id: int):
    return fetch(
        "SELECT * FROM users WHERE id = %s",
        (user_id,)
    )