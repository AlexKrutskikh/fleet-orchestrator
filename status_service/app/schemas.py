import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventIn(BaseModel):
    event_id: uuid.UUID
    robot_id: int
    event_type: str
    occurred_at: datetime
    payload: dict = {}


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: uuid.UUID
    robot_id: int
    event_type: str
    occurred_at: datetime
    received_at: datetime
    payload: dict


class EventPage(BaseModel):
    items: list[EventOut]
    next_cursor: str | None