from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


from app.api import auth, profile, patterns, room, analytic, admin
from app.services.stage_manager import stage_manager
from app.db.schema import ensure_schema


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
    main_router.include_router(profile.router, tags=["Profile"])
    main_router.include_router(patterns.router, tags=["Patterns"])
    main_router.include_router(room.router, tags=["Room"])
    main_router.include_router(analytic.router, tags=["Analytic"])
    main_router.include_router(admin.router, tags=["Admin"])



    @_app.get("/health")
    async def health_check():
        return {"status": "ok"}

    @_app.on_event("startup")
    async def _startup() -> None:
        ensure_schema()
        await stage_manager.start()

    @_app.on_event("shutdown")
    async def _shutdown() -> None:
        await stage_manager.stop()

    _app.include_router(main_router)
    return _app

app = create_app()


# --------------------
# RUN SERVER
# --------------------
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        #host="127.0.0.1",
        port=8000,
        reload=True
    )
