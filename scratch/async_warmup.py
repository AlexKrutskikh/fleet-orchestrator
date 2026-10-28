import asyncio
import time


async def robot(n):
    await asyncio.sleep(1)   # «робот ждёт ответа от сервера 1 секунду»
    return n


async def main():
    start = time.perf_counter()
    for i in range(10):
        await robot(i)
    print("по очереди:", round(time.perf_counter() - start, 1), "сек")

    start = time.perf_counter()
    async with asyncio.TaskGroup() as tg:
        for i in range(10):
            tg.create_task(robot(i))
    print("параллельно:", round(time.perf_counter() - start, 1), "сек")


asyncio.run(main())
