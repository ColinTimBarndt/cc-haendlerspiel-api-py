import struct
import asyncio
from lib.haendlerspiel.channels import Sender, Receiver, channel


async def first(**awaitables):
    tasks = list()
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    async def run(awt, name: str):
        result = await awt
        fut.set_result((name, result))

    for name, awt in awaitables.items():
        tasks.append(loop.create_task(run(awt, name)))

    result = await fut
    for task in tasks:
        task.cancel()
    return result


class Client:
    def __init__(self):
        self._address = None
        self._receiver = None
        self._sender = None
        self._send_channel = None
        self._recv_channel = None
        self._termination_event = None

    async def connect(self, host: str, port: int = 25252):
        if self._address:
            self.disconnect()

        reader, writer = await asyncio.open_connection(host=host, port=port)

        self._termination_event = asyncio.Event()

        self._recv_channel, recv_channel_send = channel()
        send_channel_recv, self._send_channel = channel()

        async def receiver(reader, sender: Sender, terminate: asyncio.Event):
            async def read_packet():
                header = await reader.read(6)
                if len(header) != 6:
                    terminate.set()
                    return None
                try:
                    pid, body_len = struct.unpack("<HI", header)
                    body = await reader.read(body_len)
                    if len(body) != body_len:
                        terminate.set()
                        return None
                    return (pid, body)
                except struct.error as _err:
                    terminate.set()
                    return None

            while True:
                type, packet = await first(terminate=terminate.wait(), packet=read_packet())
                if type == "terminate":
                    break
                elif type == "packet":
                    if packet == None:
                        continue
                    print("Received packet", repr(packet))

        async def sender(writer, receiver: Receiver, terminate: asyncio.Event):
            while True:
                type, packet = await first(
                    terminate=terminate.wait(), packet=receiver.receive())
                print(type)
                if type == "terminate":
                    break
                elif type == "packet":
                    body = packet.write_packet()
                    data = struct.pack("<HI", packet.SEND_ID, len(body)) + body
                    writer.write(data)
                    await writer.drain()
            writer.close()
            await writer.wait_closed()

        loop = asyncio.get_running_loop()

        self._receiver = loop.create_task(
            receiver(reader, recv_channel_send, self._termination_event), name="Client TCP:HSP Receiver")

        self._sender = loop.create_task(
            sender(writer, send_channel_recv, self._termination_event), name="Client TCP:HSP Sender")

        self._address = (host, port)

    async def disconnect(self):
        if not self._address:
            return

        self._termination_event.set()
        await asyncio.wait((self._receiver, self._sender))

        self._termination_event = None
        self._address = None
        self._receiver = None
        self._sender = None
        self._send_channel = None
        self._recv_channel = None
        self._termination_event = None

    async def send_packet(self, packet):
        assert self._address != None, "Client is not connected"
        assert packet.SEND_ID >= 0, "Packet `{0}` can't be sent".format(
            packet.__name__)
        await self._send_channel.send(packet)
