import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import httpx
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .api import router
from .config import settings
from .consumer import EventConsumer
from .db import engine, get_session
from .reports import router as reports_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)

consumer = EventConsumer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.django = httpx.AsyncClient(
        base_url=settings.django_api_url, timeout=5, trust_env=False
    )
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await consumer.start()
    yield
    await consumer.stop()
    await app.state.redis.aclose()
    await app.state.django.aclose()
    await engine.dispose()


app = FastAPI(title="Fleet Status Service", lifespan=lifespan)
app.include_router(router)
app.include_router(reports_router)

@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}