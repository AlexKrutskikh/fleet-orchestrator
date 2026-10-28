import os
from pathlib import Path

from crewai import LLM, Agent, Crew, Process, Task
from crewai_tools import MCPServerAdapter
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

READ_ONLY_TOOLS = {"list_robots", "get_robot", "robot_events", "robot_health_report", "count_robots"}

llm = LLM(
    model=f"openai/{os.getenv('OLLAMA_MODEL', 'gpt-oss:120b')}",
    base_url="https://ollama.com/v1",        # облако Ollama через совместимый с OpenAI адрес
    api_key=os.environ["OLLAMA_API_KEY"],
)

server_params = {
    "url": os.getenv("MCP_URL", "http://127.0.0.1:9000/mcp"),
    "transport": "streamable-http",
}


def main():
    with MCPServerAdapter(server_params) as mcp_tools:
        tools = [t for t in mcp_tools if t.name in READ_ONLY_TOOLS]
        print("Инструменты сборщика:", [t.name for t in tools])

        collector = Agent(
            role="Сборщик данных о роботах",
            goal="Собрать полную и точную статистику по роботам за период",
            backstory="Аккуратный инженер эксплуатации. Собирает факты, выводов не делает.",
            tools=tools,
            llm=llm,
        )
        analyst = Agent(
            role="Аналитик надёжности RPA-роботов",
            goal="Найти проблемных роботов и вероятные причины сбоев",
            backstory="Опытный инженер, который по статистике и событиям находит причины проблем.",
            llm=llm,
        )
        writer = Agent(
            role="Автор отчётов для руководства",
            goal="Написать короткий и понятный отчёт без технического жаргона",
            backstory="Умеет объяснять технические проблемы простым языком.",
            llm=llm,
        )

        collect = Task(
            description=(
                "Собери данные о роботах за последние {days} дней: отчёт о надёжности "
                "и последние события трёх самых проблемных роботов."
            ),
            expected_output="Таблица по роботам: команды, процент падений, время выполнения; события проблемных роботов.",
            agent=collector,
        )
        analyze = Task(
            description=(
                "По собранным данным найди проблемных роботов. "
                "Для каждого вывода укажи, на каких именно данных он основан. "
                "Если у робота меньше 20 команд за период, прямо напиши, что данных недостаточно для выводов. "
                "Не придумывай причины, которых нет в данных: если причина неизвестна, так и напиши."
            ),
            expected_output="Список проблем с указанием данных, на которых основан каждый вывод, и уровня уверенности.",
            agent=analyst,
            context=[collect],
        )
        report = Task(
            description="Напиши отчёт о работе роботов за последние {days} дней для руководителя.",
            expected_output="Отчёт в Markdown: краткий итог, главные проблемы, рекомендации.",
            agent=writer,
            context=[analyze],
            output_file=str(BASE_DIR / "reports" / "weekly_report.md"),
        )

        crew = Crew(
            agents=[collector, analyst, writer],
            tasks=[collect, analyze, report],
            process=Process.sequential,
            verbose=True,
        )
        result = crew.kickoff(inputs={"days": 7})
        print("\n===== ОТЧЁТ =====\n")
        print(result.raw)


if __name__ == "__main__":
    main()