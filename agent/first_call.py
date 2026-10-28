import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from ollama import AsyncClient

load_dotenv(Path(__file__).with_name(".env"))
MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5")


async def main():
    client = AsyncClient(trust_env=False)   # localhost, системный прокси не нужен

    response = await client.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты помощник оператора системы управления RPA-роботами. "
                    "RPA-робот — это программа (Python-процесс) на сервере или рабочем месте, "
                    "которая автоматизирует бизнес-процессы, а не физическое устройство. "
                    "Роботы раз в 5 секунд отправляют heartbeat по HTTP на сервер оркестратора "
                    "(Django REST API) и получают от него команды. "
                    "Отвечай кратко и по-русски."
                ),
            },
            {
                "role": "user",
                "content": "Робот перестал присылать heartbeat. Какие три причины проверить первыми?",
            },
        ],
        think=False,
        options={"num_predict": 500},
    )

    print(response.message.content)
    print("размышления:", response.message.thinking)
    print("---")
    print("done_reason:", response.done_reason)
    print("токены: вход", response.prompt_eval_count, "/ выход", response.eval_count)


asyncio.run(main())