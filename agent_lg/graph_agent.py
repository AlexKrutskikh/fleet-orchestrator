import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

load_dotenv(Path(__file__).with_name(".env"))

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:9000/mcp")

DANGEROUS_TOOLS = {"send_command"}

SYSTEM_PROMPT = (
    "Ты помощник оператора системы управления RPA-роботами. "
    "Для любых вопросов о конкретных роботах используй инструменты и не выдумывай данные. "
    "Если инструмент вернул ошибку в аргументах, исправь их и попробуй снова. "
    "Если пользователь отклонил вызов, сообщи об этом и не повторяй его. "
    "Отвечай кратко и по-русски."
)


def make_llm() -> ChatOllama:
    kwargs = {"model": MODEL, "base_url": OLLAMA_HOST}
    if OLLAMA_API_KEY:
        kwargs["client_kwargs"] = {"headers": {"Authorization": f"Bearer {OLLAMA_API_KEY}"}}
    return ChatOllama(**kwargs)


async def build_graph():
    # Инструменты берём с нашего MCP-сервера
    mcp_client = MultiServerMCPClient(
        {"fleet": {"transport": "streamable_http", "url": MCP_URL}}
    )
    tools = await mcp_client.get_tools()
    model = make_llm().bind_tools(tools)

    # ---------- Узлы ----------

    async def agent(state: MessagesState):
        """Спросить модель."""
        response = await model.ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    def approve(state: MessagesState) -> Command:
        """Спросить человека, если модель хочет вызвать опасный инструмент."""
        last = state["messages"][-1]
        dangerous = [call for call in last.tool_calls if call["name"] in DANGEROUS_TOOLS]
        if not dangerous:
            return Command(goto="tools")

        decision = interrupt([{"name": c["name"], "args": c["args"]} for c in dangerous])
        if decision == "yes":
            return Command(goto="tools")

        rejected = [
            ToolMessage(content="Пользователь отклонил вызов", tool_call_id=c["id"], name=c["name"])
            for c in last.tool_calls
        ]
        return Command(goto="agent", update={"messages": rejected})

    # ---------- Граф ----------

    def route_after_agent(state: MessagesState) -> str:
        return "approve" if state["messages"][-1].tool_calls else END

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    builder.add_node("approve", approve)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent, ["approve", END])
    builder.add_edge("tools", "agent")
    # из approve переходы задаются через Command(goto=...)

    return builder.compile(checkpointer=InMemorySaver())


def print_update(node: str, update: dict | None):
    for message in (update or {}).get("messages", []):
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                print(f"  [{node}] вызов {call['name']}({call['args']})")
        elif isinstance(message, ToolMessage):
            print(f"  [{node}] ← {str(message.content)[:300]}")
        elif isinstance(message, AIMessage):
            print("Агент:", message.content)


async def run_turn(graph, payload, config) -> list | None:
    """Прогнать граф до конца или до остановки. Возвращает данные остановки, если она была."""
    interrupted = None
    async for chunk in graph.astream(payload, config, stream_mode="updates"):
        for node, update in chunk.items():
            if node == "__interrupt__":
                interrupted = update[0].value
            else:
                print_update(node, update)
    return interrupted


async def main():
    graph = await build_graph()
    print(graph.get_graph().draw_mermaid())   # схема графа в формате Mermaid

    config = {"configurable": {"thread_id": "operator-1"}, "recursion_limit": 20}
    print("Агент на LangGraph готов. Пустая строка — выход.")

    while True:
        text = (await asyncio.to_thread(input, "\nВы: ")).strip()
        if not text:
            break

        payload = {"messages": [HumanMessage(text)]}
        while True:
            interrupted = await run_turn(graph, payload, config)
            if interrupted is None:
                break
            answer = await asyncio.to_thread(
                input, f"\n⚠ Модель хочет вызвать {interrupted}. Разрешить? [y/N]: "
            )
            approved = answer.strip().lower() in ("y", "yes", "д", "да")
            payload = Command(resume="yes" if approved else "no")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nАгент остановлен")