from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_app.api.routers import admin, auth, members, org

app = FastAPI(title="Crawl Platform API")

_origins = [o.strip() for o in os.environ.get("API_CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(org.router)
app.include_router(members.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
