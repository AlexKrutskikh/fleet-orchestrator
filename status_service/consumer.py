import asyncio
import json
import logging
import os
from pathlib import Path

import aio_pika
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://fleet:fleet@localhost:5672/")
EVENTS_EXCHANGE = "fleet.events"
QUEUE_NAME = "status_service.events"
PREFETCH = 50

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("consumer")


async def handle(message: aio_pika.abc.AbstractIncomingMessage):
    event = json.loads(message.body)
    log.info(
        "%-32s робот %-3s %s",
        message.routing_key, event["robot_id"], event["payload"],
    )


async def main():
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=PREFETCH)

        exchange = await channel.declare_exchange(
            EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.bind(exchange, routing_key="robot.#")
        log.info("Очередь %s готова, жду события...", QUEUE_NAME)

        async with queue.iterator() as messages:
            async for message in messages:
                async with message.process():
                    await handle(message)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Консьюмер остановлен")