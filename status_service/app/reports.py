from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import BigInteger, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import visible_robots
from .db import get_session

router = APIRouter(prefix="/reports", tags=["reports"])

HEALTH_SQL = text("""
    WITH commands AS (
        SELECT
            payload->>'command_id' AS command_id,
            min(robot_id) AS robot_id,
            max(occurred_at) FILTER (WHERE event_type IN ('command.completed', 'command.failed'))
              - max(occurred_at) FILTER (WHERE event_type = 'command.received') AS duration,
            bool_or(event_type = 'command.failed') AS failed
        FROM robot_events
        WHERE robot_id = ANY(:robot_ids)
          AND occurred_at > now() - make_interval(days => :days)
          AND event_type LIKE 'command.%'
          AND payload->>'command_id' IS NOT NULL
        GROUP BY payload->>'command_id'
    )
    SELECT
        robot_id,
        count(*) AS commands,
        round(100.0 * count(*) FILTER (WHERE failed) / count(*), 1) AS fail_pct,
        round((percentile_cont(0.5)  WITHIN GROUP (ORDER BY extract(epoch FROM duration)))::numeric, 2) AS p50_sec,
        round((percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM duration)))::numeric, 2) AS p95_sec,
        rank() OVER (ORDER BY count(*) FILTER (WHERE failed)::float / count(*) DESC) AS fail_rank
    FROM commands
    WHERE duration IS NOT NULL
    GROUP BY robot_id
    ORDER BY fail_rank
    LIMIT :limit
""").bindparams(bindparam("robot_ids", type_=ARRAY(BigInteger)))


class RobotHealth(BaseModel):
    robot_id: int
    robot_name: str
    commands: int
    fail_pct: float
    p50_sec: float | None
    p95_sec: float | None
    fail_rank: int


@router.get("/robot-health", response_model=list[RobotHealth])
async def robot_health(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(10, ge=1, le=100),
    robots: dict[int, str] = Depends(visible_robots),
    session: AsyncSession = Depends(get_session),
):
    if not robots:
        return []

    result = await session.execute(
        HEALTH_SQL, {"robot_ids": list(robots), "days": days, "limit": limit}
    )
    return [
        RobotHealth(robot_name=robots[row.robot_id], **row._mapping)
        for row in result
    ]