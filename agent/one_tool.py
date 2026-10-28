import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from ollama import AsyncClient

load_dotenv(Path(__file__).with_name(".env"))
MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:2b-q4_K_M")
FLEET_API = os.getenv("FLEET_API", "http://127.0.0.1:8000")
FLEET_USER = os.getenv("FLEET_USER", "alice")
FLEET_PASSWORD = os.getenv("FLEET_PASSWORD", "")

ROBOT_STATUSES = ["offline", "idle", "busy", "paused", "stopping"]

SYSTEM_PROMPT = (
    "Ты помощник оператора системы управления RPA-роботами. "
    "RPA-робот — это программа на сервере или рабочем месте, а не физическое устройство. "
    "Роботы присылают heartbeat на сервер оркестратора и получают от него команды. "
    "Для любых вопросов о конкретных роботах используй инструменты и не выдумывай данные. "
    "Отвечай кратко и по-русски."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_robots",
            "description": (
                "Возвращает список RPA-роботов пользователя: имя, статус, команду "
                "и время последнего heartbeat. Можно отфильтровать по статусу."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ROBOT_STATUSES,
                        "description": "Показать только роботов с этим статусом",
                    },
                },
                "required": [],
            },
        },
    },
]


async def login(api: httpx.AsyncClient):
    resp = await api.post(
        "/api/auth/token/", json={"username": FLEET_USER, "password": FLEET_PASSWORD}
    )
    resp.raise_for_status()
    api.headers["Authorization"] = f"Bearer {resp.json()['access']}"


async def list_robots(api: httpx.AsyncClient, args: dict) -> list[dict] | dict:
    status = args.get("status")
    if status is not None and status not in ROBOT_STATUSES:
        return {"error": f"Недопустимый статус: {status}"}

    params = {"status": status} if status else {}
    resp = await api.get("/api/robots/", params=params)
    resp.raise_for_status()
    return [
        {
            "name": r["name"],
            "status": r["status"],
            "team": r["team_name"],
            "last_heartbeat_at": r["last_heartbeat_at"],
        }
        for r in resp.json()["results"]
    ]


async def main():
    question = "Какие роботы сейчас на паузе?"
    print("Вопрос:", question)

    async with httpx.AsyncClient(base_url=FLEET_API, timeout=10, trust_env=False) as api:
        await login(api)
        llm = AsyncClient(trust_env=False)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        # 1. Модель решает, нужен ли инструмент
        response = await llm.chat(model=MODEL, messages=messages, tools=TOOLS, think=False)
        if not response.message.tool_calls:
            print("Инструмент не понадобился. Ответ:", response.message.content)
            return

        messages.append(response.message)   # просьба модели становится частью истории

        # 2. Наш код выполняет то, что попросила модель
        for call in response.message.tool_calls:
            name, args = call.function.name, call.function.arguments
            print(f"Модель просит вызвать: {name}({args})")

            if name == "list_robots":
                result = await list_robots(api, args)
            else:
                result = {"error": f"Неизвестный инструмент: {name}"}

            print("Результат инструмента:", result)
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result, ensure_ascii=False),
            })

        # 3. Модель отвечает уже по реальным данным
        response = await llm.chat(model=MODEL, messages=messages, tools=TOOLS, think=False)
        print("Ответ:", response.message.content)


asyncio.run(main())