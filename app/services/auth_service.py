from typing import Dict

# временная "база"
USERS_DB: Dict[str, str] = {
    "admin": "1234",
    "test": "1111"
}


def check_user(username: str, password: str) -> bool:
    return USERS_DB.get(username) == password


def create_fake_token(username: str) -> str:
    # заглушка вместо JWT
    return f"token_{username}"