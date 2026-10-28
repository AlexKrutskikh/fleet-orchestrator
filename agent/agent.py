import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp import Client
from ollama import AsyncClient

load_dotenv(Path(__file__).with_name(".env"))

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:9000/mcp")


def parse_think(value: str) -> bool | str:
    value = value.strip().lower()
    if value in ("false", "0", "no", ""):
        return False
    if value in ("true", "1", "yes"):
        return True
    return value


THINK = parse_think(os.getenv("OLLAMA_THINK", "low"))
MAX_STEPS = 8

# Инструменты только для чтения хост разрешает сам. Остальные — после подтверждения человеком.
AUTO_APPROVE = {"list_robots", "get_robot", "robot_health_report", "robot_events"}

SYSTEM_PROMPT = (
    "Ты помощник оператора системы управления RPA-роботами. "
    "Для любых вопросов о конкретных роботах используй инструменты и не выдумывай данные. "
    "Если инструмент вернул ошибку в аргументах, исправь их и попробуй снова. "
    "Если пользователь отклонил вызов, сообщи об этом и не повторяй его. "
    "Отвечай кратко и по-русски."
)


def make_llm() -> AsyncClient:
    if OLLAMA_API_KEY:
        return AsyncClient(host=OLLAMA_HOST, headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"})
    return AsyncClient(host=OLLAMA_HOST, trust_env=False)


def to_ollama_tools(mcp_tools) -> list[dict]:
    """Описания инструментов MCP → формат инструментов Ollama."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }
        for tool in mcp_tools
    ]


def result_to_text(result) -> str:
    """Результат MCP-инструмента → текст для модели."""
    if result.structured_content is not None:
        return json.dumps(result.structured_content, ensure_ascii=False, default=str)
    return "\n".join(getattr(block, "text", "") for block in result.content)


async def approve(name: str, args: dict) -> bool:
    answer = await asyncio.to_thread(
        input, f"\n⚠ Модель хочет вызвать {name}({args}). Разрешить? [y/N]: "
    )
    return answer.strip().lower() in ("y", "yes", "д", "да")


async def call_mcp_tool(mcp_client: Client, name: str, args: dict) -> str:
    if name not in AUTO_APPROVE and not await approve(name, args):
        return json.dumps({"error": "Пользователь отклонил вызов"}, ensure_ascii=False)
    try:
        result = await mcp_client.call_tool(name, args)
    except Exception as exc:
        return json.dumps({"error": f"Ошибка MCP-сервера: {exc}"}, ensure_ascii=False)
    text = result_to_text(result)
    return f"Ошибка: {text}" if result.is_error else text


async def run_agent(llm: AsyncClient, mcp_client: Client, tools: list[dict], messages: list) -> str:
    for step in range(1, MAX_STEPS + 1):
        print(f"  [шаг {step}] модель думает...", flush=True)
        response = await llm.chat(model=MODEL, messages=messages, tools=tools, think=THINK)
        messages.append(response.message)

        if response.done_reason == "length":
            return "Ответ модели обрезан по лимиту токенов."
        if not response.message.tool_calls:
            return response.message.content

        for call in response.message.tool_calls:
            name, args = call.function.name, call.function.arguments or {}
            print(f"  [шаг {step}] MCP → {name}({args})")
            content = await call_mcp_tool(mcp_client, name, args)
            print(f"  [шаг {step}] ← {content[:300]}")
            messages.append({"role": "tool", "tool_name": name, "content": content})

    return "Агент не уложился в лимит шагов и остановлен."


async def expand_command(mcp_client: Client, text: str) -> str:
    """Команда /investigate <робот> превращается в шаблон investigate_robot с MCP-сервера."""
    if text.startswith("/investigate "):
        robot = text.split(maxsplit=1)[1]
        prompt = await mcp_client.get_prompt("investigate_robot", {"name": robot})
        expanded = "\n".join(message.content.text for message in prompt.messages)
        print(f"  [шаблон] {expanded}")
        return expanded
    return text


async def main():
    llm = make_llm()
    async with Client(MCP_URL) as mcp_client:
        listed = await mcp_client.list_tools()
        tools = to_ollama_tools(listed.tools)

        print(f"Подключён к MCP-серверу {MCP_URL}. Модель: {MODEL}.")
        print("Инструменты сервера:", ", ".join(t["function"]["name"] for t in tools))
        print("Команда /investigate <робот> — разбор робота по шаблону. Пустая строка — выход.")

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        while True:
            text = (await asyncio.to_thread(input, "\nВы: ")).strip()
            if not text:
                break
            messages.append({"role": "user", "content": await expand_command(mcp_client, text)})
            answer = await run_agent(llm, mcp_client, tools, messages)
            print("Агент:", answer)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nАгент остановлен")