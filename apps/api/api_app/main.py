"""Agentic MLOps API — FastAPI application entry point."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_app.routers.agent import router as agent_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: setup and teardown."""
    # Startup
    from shared_lib.logging import setup_logging
    from shared_lib.telemetry import setup_telemetry

    setup_logging()
    setup_telemetry(service_name="agentic-mlops-api")
    yield
    # Shutdown


app = FastAPI(
    title="Agentic MLOps Platform",
    version="0.1.0",
    description="Code-First AI Agent-driven ML Modeling Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
