import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from ollama import AsyncClient, ResponseError

load_dotenv(Path(__file__).with_name(".env"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://ollama.com")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
MODEL = os.getenv("OLLAMA_MODEL", "")


async def main():
    if not OLLAMA_API_KEY:
        raise SystemExit("Задайте OLLAMA_API_KEY в agent/.env")

    client = AsyncClient(
        host=OLLAMA_HOST,
        headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
    )

    # 1. Проверяем ключ: просим список доступных облачных моделей
    try:
        models = await client.list()
    except ResponseError as exc:
        raise SystemExit(f"Ошибка доступа ({exc.status_code}): {exc.error}")

    names = [m.model for m in models.models]
    print(f"Ключ работает. Доступно моделей: {len(names)}")
    for name in names:
        print("  -", name)

    if not MODEL:
        print("\nOLLAMA_MODEL не задан: выберите имя из списка выше и впишите в agent/.env")
        return

    # 2. Проверяем модель: короткий вопрос
    print(f"\nСпрашиваю модель {MODEL}...")
    try:
        response = await client.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Отвечай кратко и по-русски."},
                {"role": "user", "content": "Ответь одним словом: ты на связи?"},
            ],
            think=False,
        )
    except ResponseError as exc:
        raise SystemExit(f"Ошибка модели ({exc.status_code}): {exc.error}")

    print("Ответ:", response.message.content)
    print("done_reason:", response.done_reason)
    print("токены: вход", response.prompt_eval_count, "/ выход", response.eval_count)


asyncio.run(main())