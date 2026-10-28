# Fleet Orchestrator

Учебная система управления RPA-роботами.

## Структура
- core/ — Django + DRF, приложения accounts, robots, jobs, events. База fleet.
- status_service/ — FastAPI + SQLAlchemy async + Alembic, история событий. База fleet_status.
- fleet_mcp/ — MCP-сервер поверх API.
- emulator/ — асинхронный эмулятор роботов.
- agent/, agent_lg/, crew_report/ — агенты.

## Важное
- Права: TeamScopedQuerysetMixin (видимость по командам) и HasTeamRole (роль для действия).
- Выдача заданий роботам: select_for_update(skip_locked=True) в RobotAgentViewSet.next_job.

## Правила
- Перед изменениями опиши план и дождись подтверждения.
- Маленькие шаги. Не меняй файлы, о которых не просили.
- Тесты — pytest и pytest-django.
- Никогда не коммить .env, robots.json и папки виртуальных окружений.
- Отвечай по-русски.