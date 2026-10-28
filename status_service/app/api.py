import base64
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import require_robot_access
from .db import get_session
from .models import RobotEvent
from .schemas import EventOut, EventPage

router = APIRouter(prefix="/robots", tags=["events"])


def encode_cursor(event: RobotEvent) -> str:
    raw = json.dumps({"t": event.occurred_at.isoformat(), "id": event.id})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(data["t"]), int(data["id"])
    except (ValueError, KeyError):
        raise HTTPException(status_code=400, detail="Некорректный курсор")


@router.get(
    "/{robot_id}/events",
    response_model=EventPage,
    dependencies=[Depends(require_robot_access)],
)
async def robot_events(
    robot_id: int,
    event_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(RobotEvent).where(RobotEvent.robot_id == robot_id)

    if event_type:
        stmt = stmt.where(RobotEvent.event_type == event_type)

    if cursor:
        last_time, last_id = decode_cursor(cursor)
        stmt = stmt.where(
            tuple_(RobotEvent.occurred_at, RobotEvent.id) < tuple_(last_time, last_id)
        )

    stmt = stmt.order_by(RobotEvent.occurred_at.desc(), RobotEvent.id.desc()).limit(limit + 1)
    events = (await session.scalars(stmt)).all()

    has_more = len(events) > limit
    events = events[:limit]

    return EventPage(
        items=[EventOut.model_validate(e) for e in events],
        next_cursor=encode_cursor(events[-1]) if has_more else None,
    )