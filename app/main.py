from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
import uvicorn


from app.api import auth, home

import os
from dotenv import load_dotenv

load_dotenv(override=False)




def create_app() -> FastAPI:
    app = FastAPI(title="Stoloto Project")

    origins = os.getenv("CORS_ORIGINS", "").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
