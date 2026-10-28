import asyncio
import json
import uuid
from datetime import datetime, timezone

import aio_pika

COUNT = 1000


async def main():
    connection = await aio_pika.connect_robust("amqp://fleet:fleet@localhost:5672/")
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            "fleet.events", aio_pika.ExchangeType.TOPIC, durable=True
        )
        for i in range(COUNT):
            event = {
                "event_id": str(uuid.uuid4()),
                "robot_id": i % 10 + 1,
                "event_type": "test.flood",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"n": i},
            }
            await exchange.publish(
                aio_pika.Message(body=json.dumps(event).encode()),
                routing_key=f"robot.{event['robot_id']}.test.flood",
            )
    print(f"Опубликовано {COUNT} событий")


asyncio.run(main())