from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi import Request
import uvicorn

from app.api import auth, home


def create_app() -> FastAPI:
    app = FastAPI(title="Stoloto Project")

    # routers
    app.include_router(auth.router, tags=["Auth"])
    app.include_router(home.router, tags=["Home"])

    @app.get("/")
    def root(request: Request):
        user_id = request.cookies.get("user_id")

        if user_id:
            return RedirectResponse(url="/home")
        return RedirectResponse(url="/auth/login")

    return app


app = create_app()


# --------------------
# RUN SERVER
# --------------------
#if __name__ == "__main__":
#    uvicorn.run(
#        "app.main:app",
#        host="127.0.0.1",
#        port=8000,
#        reload=True
#    )
