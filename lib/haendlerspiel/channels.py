from asyncio import Event, Lock
from collections import deque


def channel():
    lock = Lock()
    event = Event()
    buffer = deque()
    return (Receiver(lock, event, buffer), Sender(lock, event, buffer))


class Receiver:
    def __init__(self, l, e, b):
        self._lock = l
        self._event = e
        self._buffer = b

    async def receive(self):
        await self._event.wait()
        async with self._lock:
            if len(self._buffer) == 1:
                self._event.clear()
            return self._buffer.popleft()


class Sender:
    def __init__(self, l, e, b):
        self._lock = l
        self._event = e
        self._buffer = b

    async def send(self, data):
        async with self._lock:
            self._buffer.append(data)
            self._event.set()
