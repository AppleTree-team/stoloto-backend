from fastapi import FastAPI, APIRouter
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
import uvicorn


from app.api import auth, home

import os
from dotenv import load_dotenv

load_dotenv(override=False)




def create_app() -> FastAPI:
    _app = FastAPI(title="Stoloto Project")

    origins = os.getenv("CORS_ORIGINS", "").split(",")
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # routers
    main_router = APIRouter(prefix="/api")
    main_router.include_router(auth.router, tags=["Auth"])
    main_router.include_router(home.router, tags=["Home"])

    @_app.get("/health")
    async def health_check():
        return {"status": "ok"}

    _app.include_router(main_router)
    return _app

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
