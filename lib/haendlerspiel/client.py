import struct
import asyncio
from lib.haendlerspiel.sync import Sender, Receiver, channel, Mutex
import lib.haendlerspiel.packet as packet
from lib.haendlerspiel.serial import ConnectionState
import random
import time

_packets = packet.packets


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
        self._state = None

        self._packet_listeners = dict()

    async def connect(self, host: str, port: int = 25252):
        if self._address:
            self.disconnect()

        reader, writer = await asyncio.open_connection(host=host, port=port)

        self._termination_event = asyncio.Event()

        self._state = Mutex(ConnectionState.HANDSHAKE)

        self._recv_channel, recv_channel_send = channel()
        send_channel_recv, self._send_channel = channel()

        async def receiver(reader, sender: Sender, state: Mutex, terminate: asyncio.Event):
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
                f_type, packet = await first(terminate=terminate.wait(), packet=read_packet())
                if f_type == "terminate":
                    return
                elif f_type == "packet":
                    del f_type
                    if packet == None:
                        return
                    async with state as s:
                        packet = _packets.read_packet(
                            state=s.value,
                            packet_id=packet[0],
                            buffer=packet[1]
                        )
                    print(f"Received packet {type(packet).__name__}")
                    if type(packet) in self._packet_listeners:
                        ls = self._packet_listeners[type(packet)]
                        for l, _uid in ls:
                            try:
                                l(packet)
                            except Exception as ex:
                                print("Error in listener:")
                                print(ex)

        async def sender(writer, receiver: Receiver, state: Mutex, terminate: asyncio.Event):
            try:
                while True:
                    type, packet = await first(
                        terminate=terminate.wait(), packet=receiver.receive())
                    if type == "terminate":
                        break
                    elif type == "packet":
                        body = packet.write_packet()
                        data = struct.pack(
                            "<HI", packet.SEND_ID, len(body)) + body
                        writer.write(data)
                        await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        loop = asyncio.get_running_loop()

        self._receiver = loop.create_task(
            receiver(reader, recv_channel_send, self._state, self._termination_event), name="Client TCP:HSP Receiver")

        self._sender = loop.create_task(
            sender(writer, send_channel_recv, self._state, self._termination_event), name="Client TCP:HSP Sender")

        self._address = (host, port)

    async def ping(self):
        """Pings the server and returns the result.

        This is only possible if the connection state is HANDSHAKE.
        This function will close the connection to the server.

        Returns
        -------
        (int, PingStatusPacket)
            Ping in nanoseconds and server status.
        """
        handshake_packet = packet.HandshakePacket(
            packet.HandshakePacket.Action.PING)
        ping_packet = packet.PingPongPacket()
        async with self._state as state:
            state.value = ConnectionState.PING

        ping = time.time_ns()

        status_packet = await self._once_packet(packet.PingStatusPacket, send_packet=handshake_packet)
        pong_packet = await self._once_packet(packet.PingPongPacket, send_packet=ping_packet)

        ping = time.time_ns() - ping

        await self.disconnect()

        if ping_packet.random != pong_packet.random:
            # Invalid ping response
            ping = None

        return (ping, status_packet)

    async def encrypt(self):
        """Encrypts the connection in order to log in.

        This is only possible if the connection state is HANDSHAKE.
        This function will set the connection state to LOGIN.
        """
        async with self._state as state:
            state.value = ConnectionState.ENCRYPT

        handshake_packet = packet.HandshakePacket(
            packet.HandshakePacket.Action.CONNECT)

        encryption_req_packet = await self._once_packet(packet.RequestEncryption, send_packet=handshake_packet)
        encryption_resp_packet, secret = encryption_req_packet.create_response()
        print("SECRET:", secret.hex())
        await self.send_packet(encryption_resp_packet)

        print("Success!")

    def _on_packet(self, packet, cb, *, once=False):
        ls = None
        if not packet in self._packet_listeners:
            ls = list()
            self._packet_listeners[packet] = ls
        else:
            ls = self._packet_listeners[packet]

        uid = time.time_ns()

        def f(p):
            cb(p)
            if once:
                ls.remove((f, uid))
        ls.append((f, uid))

    async def _once_packet(self, packet, *, send_packet=None):
        fut = asyncio.get_running_loop().create_future()

        def cb(p):
            fut.set_result(p)
        self._on_packet(packet, cb, once=True)
        if not send_packet is None:
            await self.send_packet(send_packet)
        return await fut

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
        self._state = None

    async def send_packet(self, packet):
        assert self._address != None, "Client is not connected"
        assert packet.SEND_ID >= 0, "Packet `{0}` can't be sent".format(
            packet.__name__)
        await self._send_channel.send(packet)
