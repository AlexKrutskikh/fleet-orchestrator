import asyncio
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "emulator" / ".env")

API = os.getenv("FLEET_API", "http://127.0.0.1:8000")
ADMIN_USER = os.getenv("FLEET_ADMIN_USER", "alice")
ADMIN_PASSWORD = os.getenv("FLEET_ADMIN_PASSWORD", "")
TEAM_ID = int(os.getenv("FLEET_TEAM_ID", "1"))

JOBS = 200
WORKERS_PER_ROBOT = 5
MODE = sys.argv[1] if len(sys.argv) > 1 else "safe"   # safe или naive


async def create_jobs(client: httpx.AsyncClient, headers: dict):
    semaphore = asyncio.Semaphore(20)

    async def create(i: int):
        async with semaphore:
            resp = await client.post(
                "/api/jobs/",
                headers=headers,
                json={"team": TEAM_ID, "job_type": "emulator", "payload": {"race": i}, "priority": 5},
            )
            resp.raise_for_status()

    async with asyncio.TaskGroup() as tg:
        for i in range(JOBS):
            tg.create_task(create(i))


async def worker(client: httpx.AsyncClient, api_key: str, claims: list):
    headers = {"Authorization": f"Robot {api_key}"}
    params = {"mode": "naive"} if MODE == "naive" else {}
    while True:
        resp = await client.post("/api/robot/jobs/next/", headers=headers, params=params)
        if resp.status_code == 204:
            return
        resp.raise_for_status()
        claims.append(resp.json()["job"]["id"])


async def main():
    robots = json.loads((ROOT / "emulator" / "robots.json").read_text(encoding="utf-8"))
    limits = httpx.Limits(max_connections=100)

    async with httpx.AsyncClient(base_url=API, timeout=30, trust_env=False, limits=limits) as client:
        resp = await client.post(
            "/api/auth/token/", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD}
        )
        resp.raise_for_status()
        await create_jobs(client, {"Authorization": f"Bearer {resp.json()['access']}"})
        print(f"Создано заданий: {JOBS}")

        claims: list[int] = []
        start = time.perf_counter()
        async with asyncio.TaskGroup() as tg:
            for robot in robots:
                for _ in range(WORKERS_PER_ROBOT):
                    tg.create_task(worker(client, robot["api_key"], claims))
        elapsed = time.perf_counter() - start

    counts = Counter(claims)
    duplicates = {job_id: n for job_id, n in counts.items() if n > 1}

    print(f"Режим: {MODE}")
    print(f"Одновременных запросов: {len(robots) * WORKERS_PER_ROBOT}")
    print(f"Всего выдач: {len(claims)}")
    print(f"Разных заданий: {len(counts)}")
    print(f"Заданий, выданных больше одного раза: {len(duplicates)}")
    if duplicates:
        worst = max(duplicates.values())
        print(f"Худший случай: одно задание выдано {worst} раз")
    print(f"Время: {elapsed:.1f} с")


asyncio.run(main())