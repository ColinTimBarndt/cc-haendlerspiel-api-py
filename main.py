from lib.haendlerspiel.client import Client
from lib.haendlerspiel.packet import Handshake, HandshakeAction
import asyncio


async def main():
    client = Client()
    await client.connect("127.0.0.1", 25252)

    await client.send_packet(Handshake(HandshakeAction.PING))

    await asyncio.sleep(2)
    await client.disconnect()

asyncio.run(main())
