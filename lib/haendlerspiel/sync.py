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


class Mutex:
    "This mutex allows synchronized access to the wrapped value"

    def __init__(self, value):
        self._value = value
        self._lock = Lock()

    async def __aenter__(self):
        await self._lock.acquire()
        val = self._value

        class MutexGuard:
            def __init__(self):
                self.value = val

        self._guard = MutexGuard()
        return self._guard

    async def __aexit__(self, typ, val, ex):
        self._value = self._guard.value
        del self._guard
        self._lock.release()
