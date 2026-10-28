import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

FLEET_API = os.getenv("FLEET_API", "http://127.0.0.1:8000")
STATUS_API = os.getenv("STATUS_API", "http://127.0.0.1:8001")
FLEET_USER = os.getenv("FLEET_USER", "alice")
FLEET_PASSWORD = os.getenv("FLEET_PASSWORD", "")

# stdout занят протоколом MCP, поэтому логи — только в stderr
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("fleet_mcp")

RobotStatus = Literal["offline", "idle", "busy", "paused", "stopping"]
Command = Literal["ping", "pause", "resume", "stop", "restart", "kill"]

mcp = MCPServer(
    "fleet",
    version="0.1.0",
    instructions=(
        "Сервер для управления RPA-роботами Fleet Orchestrator: "
        "просмотр роботов, их событий и надёжности, отправка команд."
    ),
)


# ---------- Клиент к нашим API с автоматическим повторным входом ----------

class FleetClient:
    def __init__(self):
        self._token: str | None = None
        self.django = httpx.AsyncClient(base_url=FLEET_API, timeout=10, trust_env=False)
        self.status = httpx.AsyncClient(base_url=STATUS_API, timeout=30, trust_env=False)

    async def _login(self):
        resp = await self.django.post(
            "/api/auth/token/", json={"username": FLEET_USER, "password": FLEET_PASSWORD}
        )
        resp.raise_for_status()
        self._token = resp.json()["access"]
        log.info("Вошёл в Fleet API как %s", FLEET_USER)

    async def request(self, client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
        if self._token is None:
            await self._login()
        headers = {**kwargs.pop("headers", {}), "Authorization": f"Bearer {self._token}"}
        resp = await client.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 401:
            # access-токен живёт 5 минут: входим заново и повторяем запрос один раз
            await self._login()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = await client.request(method, url, headers=headers, **kwargs)
        return resp


fleet = FleetClient()


def short_robot(r: dict) -> dict:
    return {
        "name": r["name"],
        "status": r["status"],
        "team": r["team_name"],
        "robot_type": r["robot_type"],
        "last_heartbeat_at": r["last_heartbeat_at"],
    }


async def find_robot(name: str) -> dict:
    resp = await fleet.request(fleet.django, "GET", "/api/robots/", params={"search": name})
    resp.raise_for_status()
    for r in resp.json()["results"]:
        if r["name"] == name:
            return r
    raise ValueError(f"Робот {name} не найден или недоступен пользователю")


# ---------- Инструменты ----------

@mcp.tool()
async def list_robots(statuses: list[RobotStatus] | None = None, search: str | None = None) -> list[dict]:
    """Список RPA-роботов пользователя: имя, статус, команда, время последнего heartbeat.

    Статусы: idle — робот запущен и ждёт работы, busy — выполняет задание,
    paused — на паузе, stopping — останавливается, offline — не на связи.
    «Работающие» роботы — это idle и busy.

    Args:
        statuses: показать только роботов с этими статусами
        search: часть имени робота, например emu
    """
    params: dict = {}
    if statuses:
        params["status"] = statuses
    if search:
        params["search"] = search
    resp = await fleet.request(fleet.django, "GET", "/api/robots/", params=params)
    resp.raise_for_status()
    return [short_robot(r) for r in resp.json()["results"]]


@mcp.tool()
async def get_robot(name: str) -> dict:
    """Подробная информация об одном роботе по его точному имени, например emu-003."""
    return short_robot(await find_robot(name))


@mcp.tool()
async def send_command(name: str, command: Command) -> dict:
    """Отправить роботу команду.

    ping — проверить связь, pause и resume — пауза и продолжение,
    stop — мягкая остановка, restart — перезапуск, kill — жёсткая остановка.
    Команда ставится в очередь, робот выполнит её при следующем опросе.
    Это действие меняет состояние робота.
    """
    robot = await find_robot(name)
    resp = await fleet.request(
        fleet.django,
        "POST",
        f"/api/robots/{robot['id']}/{command}/",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    if resp.status_code == 403:
        raise ValueError(f"У пользователя нет прав на команду {command} для робота {name}")
    resp.raise_for_status()
    return {
        "result": f"Команда {command} поставлена в очередь для робота {name}",
        "command_status": resp.json()["status"],
    }


@mcp.tool()
async def robot_health_report(days: int = 7, limit: int = 10) -> list[dict]:
    """Отчёт о надёжности роботов пользователя за период.

    Для каждого робота: число команд, процент неудачных (fail_pct),
    медиана (p50_sec) и 95-й перцентиль (p95_sec) времени выполнения команды
    в секундах, место в рейтинге по падениям. Отсортирован по проценту падений.

    Args:
        days: период в днях, от 1 до 90
        limit: сколько роботов показать, от 1 до 100
    """
    if not 1 <= days <= 90 or not 1 <= limit <= 100:
        raise ValueError("days должен быть от 1 до 90, limit — от 1 до 100")
    resp = await fleet.request(
        fleet.status, "GET", "/reports/robot-health", params={"days": days, "limit": limit}
    )
    resp.raise_for_status()
    return resp.json()

@mcp.tool()
def get_runbook(robot_type: str) -> str:
    """Инструкция по диагностике роботов определённого типа: известные особенности и типичные причины сбоев."""
    path = BASE_DIR / "runbooks" / f"{robot_type}.md"
    if not path.is_file():
        raise ToolError(f"Нет runbook для типа {robot_type}")
    return path.read_text(encoding="utf-8")


@mcp.tool()
async def robot_events(name: str, event_type: str | None = None, limit: int = 20) -> list[dict]:
    """Последние события робота, от новых к старым.

    Типы событий: command.received, command.completed, command.failed, status.changed.

    Args:
        name: точное имя робота
        event_type: показать только события этого типа
        limit: сколько событий вернуть, от 1 до 200
    """
    robot = await find_robot(name)
    params: dict = {"limit": min(max(limit, 1), 200)}
    if event_type:
        params["event_type"] = event_type
    resp = await fleet.request(fleet.status, "GET", f"/robots/{robot['id']}/events", params=params)
    resp.raise_for_status()
    return [
        {"event_type": e["event_type"], "occurred_at": e["occurred_at"], "payload": e["payload"]}
        for e in resp.json()["items"]
    ]


# ---------- Ресурсы ----------

@mcp.resource("fleet://system/overview")
def system_overview() -> str:
    """Как устроена система управления роботами: статусы, команды, события."""
    return (
        "Fleet Orchestrator управляет RPA-роботами. RPA-робот — программа на сервере "
        "или рабочем месте.\n\n"
        "Статусы робота: idle, busy, paused, stopping, offline.\n"
        "Жизненный цикл команды: pending (создана) → sent (робот забрал) → "
        "done или failed (робот отчитался); expired — никто не забрал вовремя.\n"
        "События робота: command.received, command.completed, command.failed, status.changed.\n"
        "Права: пользователь видит только роботов своих команд; stop, restart, kill — "
        "только для админа команды."
    )


@mcp.resource("fleet://runbooks/{robot_type}")
def runbook(robot_type: str) -> str:
    """Инструкция по диагностике роботов определённого типа."""
    path = BASE_DIR / "runbooks" / f"{robot_type}.md"
    if not path.is_file():
        raise ValueError(f"Нет runbook для типа {robot_type}")
    return path.read_text(encoding="utf-8")


# ---------- Шаблоны ----------

@mcp.prompt()
def investigate_robot(name: str) -> str:
    """Разобраться, что происходит с роботом."""
    return (
        f"Разберись, что происходит с роботом {name}. "
        "Сначала узнай его текущий статус, затем посмотри последние события. "
        "Если есть неудачные команды, сравни его процент падений с остальными роботами "
        f"через отчёт о надёжности. Прочитай runbook для его типа. "
        "В конце кратко: что происходит, вероятная причина, что рекомендуешь сделать. "
        "Не отправляй команды роботу без явной просьбы пользователя."
    )

@mcp.tool()
async def count_robots() -> dict:
    """Сколько всего роботов видит пользователь и сколько из них офлайн."""
    robots = await list_robots()
    offline = sum(1 for r in robots if r["status"] == "offline")
    return {"total": len(robots), "offline": offline}


if __name__ == "__main__":
    if "--http" in sys.argv:
        # отдельный процесс, клиенты подключаются по адресу http://127.0.0.1:9000/mcp
        mcp.run(transport="streamable-http", host="127.0.0.1", port=9000)
    else:
        mcp.run()   # stdio, как раньше — для Inspector