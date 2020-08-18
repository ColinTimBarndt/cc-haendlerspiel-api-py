from lib.haendlerspiel.client import Client
from lib.haendlerspiel.packet import HandshakePacket
import asyncio


async def main():
    client = Client()
    await client.connect("127.0.0.1", 25252)

    ping = await client.ping()
    print("Ping:", ping)

    await client.connect("127.0.0.1", 25252)

    await client.encrypt()

    await asyncio.sleep(5)
    await client.disconnect()

asyncio.run(main())
