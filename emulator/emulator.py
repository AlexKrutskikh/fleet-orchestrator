import asyncio
import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aio_pika
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

JOB_POLL_INTERVAL = 3    # секунд между попытками взять задание, если работы нет

BASE_URL = os.getenv("FLEET_API", "http://127.0.0.1:8000")
ADMIN_USER = os.getenv("FLEET_ADMIN_USER", "alice")
ADMIN_PASSWORD = os.getenv("FLEET_ADMIN_PASSWORD", "")
TEAM_ID = int(os.getenv("FLEET_TEAM_ID", "1"))
ROBOT_COUNT = int(os.getenv("FLEET_ROBOT_COUNT", "10"))
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://fleet:fleet@localhost:5672/")
KEYS_FILE = Path(__file__).with_name("robots.json")

EVENTS_EXCHANGE = "fleet.events"
HEARTBEAT_INTERVAL = 5   # секунд между heartbeat
POLL_INTERVAL = 2        # секунд между опросами команд

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("emulator")
logging.getLogger("httpx").setLevel(logging.WARNING)


class RobotStopped(Exception):
    """Робот получил stop или kill и должен завершиться."""


async def bootstrap(client: httpx.AsyncClient) -> list[dict]:
    """Создаёт роботов через API при первом запуске и сохраняет их ключи в файл."""
    if KEYS_FILE.exists():
        return json.loads(KEYS_FILE.read_text(encoding="utf-8"))

    if not ADMIN_PASSWORD:
        raise SystemExit("Задайте пароль администратора в переменной FLEET_ADMIN_PASSWORD")

    resp = await client.post(
        "/api/auth/token/", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD}
    )
    if resp.is_error:
        log.error("Не удалось получить токен: %s %s", resp.status_code, resp.text)
    resp.raise_for_status()
    headers = {"Authorization": f"Bearer {resp.json()['access']}"}

    robots = []
    for i in range(ROBOT_COUNT):
        resp = await client.post(
            "/api/robots/",
            headers=headers,
            json={"name": f"emu-{i:03d}", "team": TEAM_ID, "robot_type": "emulator"},
        )
        if resp.is_error:
            log.error("Не удалось создать робота: %s %s", resp.status_code, resp.text)
        resp.raise_for_status()
        data = resp.json()
        robots.append({"id": data["id"], "name": data["name"], "api_key": data["api_key"]})

    KEYS_FILE.write_text(json.dumps(robots, indent=2), encoding="utf-8")
    log.info("Создано роботов: %d, ключи сохранены в %s", len(robots), KEYS_FILE.name)
    return robots


class EmulatedRobot:
    def __init__(
        self,
        client: httpx.AsyncClient,
        exchange: aio_pika.abc.AbstractExchange,
        robot_id: int,
        name: str,
        api_key: str,
    ):
        self.client = client
        self.exchange = exchange
        self.robot_id = robot_id
        self.name = name
        self.headers = {"Authorization": f"Robot {api_key}"}
        self.status = "idle"

    async def run(self):
        # Разносим старты, чтобы все роботы не ударили в сервер в одну и ту же секунду
        await asyncio.sleep(random.uniform(0, HEARTBEAT_INTERVAL))
        log.info("%s: запущен", self.name)
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.heartbeat_loop())
                tg.create_task(self.command_loop())
                tg.create_task(self.job_loop())
        except* RobotStopped:
            log.info("%s: остановлен командой", self.name)
        finally:
            log.info("%s: завершил работу", self.name)

    async def heartbeat_loop(self):
        while True:
            await self.send_heartbeat()
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def command_loop(self):
        while True:
            for command in await self.fetch_commands():
                await self.execute(command)
            await asyncio.sleep(POLL_INTERVAL)

    async def send_heartbeat(self):
        try:
            resp = await self.client.post(
                "/api/robot/heartbeat/", headers=self.headers, json={"status": self.status}
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("%s: heartbeat не прошёл: %s", self.name, exc)

    async def fetch_commands(self) -> list[dict]:
        try:
            resp = await self.client.get("/api/robot/commands/", headers=self.headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            log.warning("%s: не удалось получить команды: %s", self.name, exc)
            return []

    async def complete(self, command_id: int, status: str):
        try:
            resp = await self.client.post(
                f"/api/robot/commands/{command_id}/complete/",
                headers=self.headers,
                json={"status": status},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("%s: не удалось закрыть команду #%s: %s", self.name, command_id, exc)

    async def publish_event(self, event_type: str, payload: dict | None = None):
        event = {
            "event_id": str(uuid.uuid4()),
            "robot_id": self.robot_id,
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }
        message = aio_pika.Message(
            body=json.dumps(event).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=event["event_id"],
        )
        try:
            await self.exchange.publish(
                message, routing_key=f"robot.{self.robot_id}.{event_type}"
            )
        except (aio_pika.exceptions.AMQPException, ConnectionError) as exc:
            log.warning("%s: не удалось опубликовать %s: %s", self.name, event_type, exc)

    async def set_status(self, new_status: str):
        old_status, self.status = self.status, new_status
        if old_status != new_status:
            await self.publish_event("status.changed", {"from": old_status, "to": new_status})

    async def execute(self, command: dict):
        kind = command["command_type"]
        command_info = {"command_id": command["id"], "command_type": kind}
        log.info("%s: получена команда %s (#%s)", self.name, kind, command["id"])
        await self.publish_event("command.received", command_info)

        await asyncio.sleep(random.uniform(0.5, 2))   # «выполнение» команды

        if kind in ("stop", "kill"):
            await self.set_status("stopping")
            await self.complete(command["id"], "done")
            await self.publish_event("command.completed", command_info)
            await self.send_heartbeat()
            raise RobotStopped(kind)

        if kind == "pause":
            await self.set_status("paused")
        elif kind in ("resume", "restart"):
            await self.set_status("idle")

        result = "done" if random.random() > 0.1 else "failed"   # 10% команд «падают»
        await self.complete(command["id"], result)
        event_type = "command.completed" if result == "done" else "command.failed"
        await self.publish_event(event_type, command_info)
        await self.send_heartbeat()   # сразу сообщаем новый статус, не ждём следующего цикла
        log.info("%s: команда #%s → %s, статус %s", self.name, command["id"], result, self.status)

    async def fetch_job(self) -> dict | None:
        try:
            resp = await self.client.post("/api/robot/jobs/next/", headers=self.headers)
            if resp.status_code == 204:
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            log.warning("%s: не удалось взять задание: %s", self.name, exc)
            return None

    async def finish_job(self, run_id: int, status: str, error: str = ""):
        try:
            resp = await self.client.post(
                f"/api/robot/runs/{run_id}/finish/",
                headers=self.headers,
                json={"status": status, "error_message": error},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            log.warning("%s: не удалось завершить запуск #%s: %s", self.name, run_id, exc)
            return None

    async def job_loop(self):
        while True:
            if self.status != "idle":          # на паузе или останавливается — работу не берём
                await asyncio.sleep(JOB_POLL_INTERVAL)
                continue

            task = await self.fetch_job()
            if task is None:
                await asyncio.sleep(JOB_POLL_INTERVAL)
                continue

            job, run_id = task["job"], task["run_id"]
            info = {"job_id": job["id"], "run_id": run_id, "attempt": task["attempt"]}
            log.info("%s: взял задание #%s (попытка %s)", self.name, job["id"], task["attempt"])

            await self.set_status("busy")
            await self.send_heartbeat()
            await self.publish_event("job.started", info)

            await asyncio.sleep(random.uniform(1, 4))   # «работа»

            if random.random() < 0.15:
                result = await self.finish_job(run_id, "failed", "Эмулятор: случайная ошибка")
                await self.publish_event("job.failed", info)
            else:
                result = await self.finish_job(run_id, "succeeded")
                await self.publish_event("job.completed", info)

            if result:
                log.info("%s: задание #%s → %s", self.name, job["id"], result["job_status"])
            if self.status == "busy":           # если во время работы поставили на паузу — статус не трогаем
                await self.set_status("idle")
            await self.send_heartbeat()


async def main():
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )

        limits = httpx.Limits(max_connections=50)
        async with httpx.AsyncClient(
            base_url=BASE_URL, timeout=10, limits=limits, trust_env=False
        ) as client:
            robots = await bootstrap(client)
            log.info("Запускаю роботов: %d", len(robots))
            async with asyncio.TaskGroup() as tg:
                for r in robots:
                    robot = EmulatedRobot(client, exchange, r["id"], r["name"], r["api_key"])
                    tg.create_task(robot.run())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Эмулятор остановлен (Ctrl+C)")