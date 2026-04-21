from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel

from app.services.auth_service import login

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    """Модель запроса для авторизации."""
    username: str
    password: str


@router.post("/login")
def login_endpoint(data: LoginRequest, response: Response):
    """
    Авторизация пользователя.

    При успешном входе устанавливает httpOnly cookie `session_id` с JWT токеном.

    Тело запроса (JSON):
        - username (str): Имя пользователя
        - password (str): Пароль

    Возвращает:
        - 200: {
            "message": "Login successful",
            "user_id": <id>,
            "username": "<username>"
          }
        - 401: Неверные учётные данные
        - 422: Ошибка валидации (не указаны username/password)

    Примечание:
        Cookie `session_id` автоматически подставляется в последующие запросы.
    """
    result = login(data.username, data.password)

    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response.set_cookie(
        key="session_id",
        value=result["token"],
        httponly=True
    )

    return {
        "message": "Login successful",
        "user_id": result["user_id"],
        "username": result["username"]
    }


@router.post("/logout")
def logout_endpoint(request: Request, response: Response):
    """
    Выход из системы.

    Удаляет все cookies, установленные на клиенте (включая `session_id`).

    Возвращает:
        - 200: { "message": "Logout successful, all cookies deleted" }
        - 401: (если не было активной сессии – фактически не проверяется)
    """
    for cookie in request.cookies:
        response.delete_cookie(cookie)
    return {"message": "Logout successful, all cookies deleted"}