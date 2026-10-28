import asyncio
import contextlib
import logging

import aio_pika
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert

from .config import settings
from .db import SessionLocal
from .models import RobotEvent
from .schemas import EventIn

log = logging.getLogger("status_service.consumer")

EVENTS_EXCHANGE = "fleet.events"
QUEUE_NAME = "status_service.events"


class EventConsumer:
    def __init__(self):
        # Буфер между RabbitMQ и записью в базу. Ограничен: если база не успевает,
        # обработчик сообщений будет ждать места, а не копить сообщения бесконечно.
        self._buffer: asyncio.Queue = asyncio.Queue(maxsize=settings.prefetch)
        self._connection = None
        self._queue = None
        self._consumer_tag = None
        self._writer = None

    async def start(self):
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=settings.prefetch)

        exchange = await channel.declare_exchange(
            EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        self._queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        await self._queue.bind(exchange, routing_key="robot.#")

        self._writer = asyncio.create_task(self._write_loop())
        self._consumer_tag = await self._queue.consume(self._on_message)
        log.info("Консьюмер запущен: очередь %s", QUEUE_NAME)

    async def stop(self):
        # 1. Перестаём получать новые сообщения
        if self._queue and self._consumer_tag:
            await self._queue.cancel(self._consumer_tag)
        # 2. Даём дописать то, что уже лежит в буфере
        try:
            await asyncio.wait_for(self._buffer.join(), timeout=5)
        except TimeoutError:
            log.warning("Не успели дописать буфер — сообщения вернутся в очередь")
        # 3. Останавливаем писателя и закрываем соединение
        if self._writer:
            self._writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer
        if self._connection:
            await self._connection.close()
        log.info("Консьюмер остановлен")

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        await self._buffer.put(message)

    async def _write_loop(self):
        while True:
            batch = await self._collect_batch()
            try:
                await self._flush(batch)
            finally:
                for _ in batch:
                    self._buffer.task_done()

    async def _collect_batch(self) -> list:
        """Ждёт первое сообщение, затем добирает до batch_size, но не дольше flush_interval."""
        loop = asyncio.get_running_loop()
        batch = [await self._buffer.get()]
        deadline = loop.time() + settings.flush_interval

        while len(batch) < settings.batch_size:
            timeout = deadline - loop.time()
            if timeout <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self._buffer.get(), timeout))
            except TimeoutError:
                break
        return batch

    async def _flush(self, messages: list):
        rows, valid = [], []
        for message in messages:
            try:
                event = EventIn.model_validate_json(message.body)
            except ValidationError as exc:
                log.warning("Битое сообщение отброшено: %s", exc.errors()[0]["msg"])
                await message.reject(requeue=False)
                continue
            rows.append(event.model_dump())
            valid.append(message)

        if not rows:
            return

        try:
            async with SessionLocal() as session:
                stmt = (
                    insert(RobotEvent)
                    .values(rows)
                    .on_conflict_do_nothing(index_elements=["event_id"])
                )
                result = await session.execute(stmt)
                await session.commit()
        except Exception:
            log.exception("Не удалось записать пачку из %d событий, возвращаю в очередь", len(rows))
            for message in valid:
                await message.nack(requeue=True)
            await asyncio.sleep(1)   # не долбим базу повторами без паузы
            return

        for message in valid:
            await message.ack()
        log.info("Пачка: получено %d, записано %d (дубли пропущены)", len(rows), result.rowcount)