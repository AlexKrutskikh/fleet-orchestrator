import hashlib
import json
import logging

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError

from .config import settings

log = logging.getLogger("status_service.auth")
bearer = HTTPBearer(auto_error=False)

ALLOWED = "1"
DENIED = "0"


def cache_key(token: str, robot_id: int) -> str:
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
    return f"access:{token_hash}:robot:{robot_id}"


async def cache_get(redis, key: str) -> str | None:
    try:
        return await redis.get(key)
    except RedisError as exc:
        log.warning("Redis недоступен, проверяю права без кэша: %s", exc)
        return None


async def cache_set(redis, key: str, value: str):
    try:
        await redis.set(key, value, ex=settings.access_cache_ttl)
    except RedisError as exc:
        log.warning("Не удалось сохранить в кэш: %s", exc)


async def require_robot_access(
    robot_id: int,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    """Пропускает запрос, только если пользователь из токена видит этого робота в Django."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Нужен заголовок Authorization")

    redis = request.app.state.redis
    key = cache_key(credentials.credentials, robot_id)

    # 1. Смотрим в кэш
    cached = await cache_get(redis, key)
    if cached == ALLOWED:
        return
    if cached == DENIED:
        raise HTTPException(status_code=404, detail="Робот не найден")

    # 2. Кэш пуст — спрашиваем Django
    authorization = f"{credentials.scheme} {credentials.credentials}"
    django = request.app.state.django
    resp = await django.get(f"/api/robots/{robot_id}/", headers={"Authorization": authorization})

    # 3. Запоминаем ответ (только «да» и «нет», ошибки не кэшируем)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Токен недействителен")
    if resp.status_code == 404:
        await cache_set(redis, key, DENIED)
        raise HTTPException(status_code=404, detail="Робот не найден")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Сервис прав недоступен")

    await cache_set(redis, key, ALLOWED)

async def visible_robots(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[int, str]:
    """Все роботы, которых пользователь видит в Django: {id: имя}."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Нужен заголовок Authorization")

    redis = request.app.state.redis
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()[:32]
    key = f"access:{token_hash}:robots"

    cached = await cache_get(redis, key)
    if cached is not None:
        return {int(robot_id): name for robot_id, name in json.loads(cached).items()}

    django = request.app.state.django
    headers = {"Authorization": f"{credentials.scheme} {credentials.credentials}"}
    robots: dict[int, str] = {}
    url: str | None = "/api/robots/"

    while url:
        resp = await django.get(url, headers=headers)
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Токен недействителен")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Сервис прав недоступен")
        data = resp.json()
        for robot in data["results"]:
            robots[robot["id"]] = robot["name"]
        url = data["next"]   # следующая страница пагинации DRF или None

    await cache_set(redis, key, json.dumps(robots))
    return robots