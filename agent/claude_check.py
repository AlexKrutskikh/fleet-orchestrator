import asyncio
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")


async def main():
    client = anthropic.AsyncAnthropic()   # ключ берётся из ANTHROPIC_API_KEY

    response = await client.messages.create(
        model=MODEL,
        max_tokens=500,
        system="Ты помощник оператора системы управления RPA-роботами. Отвечай кратко и по-русски.",
        messages=[{"role": "user", "content": "Ответь одним словом: ты на связи?"}],
    )

    text = "".join(block.text for block in response.content if block.type == "text")
    print("Ответ:", text)
    print("stop_reason:", response.stop_reason)
    print("токены: вход", response.usage.input_tokens, "/ выход", response.usage.output_tokens)


asyncio.run(main())