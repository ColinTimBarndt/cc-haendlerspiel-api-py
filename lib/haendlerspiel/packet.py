from enum import Enum
import struct
from lib.haendlerspiel.serial import ConnectionState
import json
from random import randint
import OpenSSL
import cryptography.hazmat.backends as backends
from secrets import token_bytes
from cryptography.hazmat.primitives.serialization import load_pem_public_key, Encoding, PublicFormat
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

NoneType = type(None)


class packets:
    send = dict()
    receive = dict()

    @classmethod
    def register(packets, packet):
        if not packet.SEND_ID is None:
            packets.send[(packet.SEND_ID, packet.SEND_STATE.value)] = packet
        if not packet.RECEIVE_ID is None:
            packets.receive[(packet.RECEIVE_ID,
                             packet.RECEIVE_STATE.value)] = packet

    @classmethod
    def read_packet(packets, state: ConnectionState, packet_id: int, buffer: bytes):
        packet_cls = packets.receive.get((packet_id, state.value))
        if packet_cls is None:
            raise Exception(
                "No packet matches state {0} and id {1}".format(state, packet_id))
        return packet_cls.read_packet(buffer)


class Packet:
    SEND_ID: set([int, NoneType]) = None
    SEND_STATE: set([ConnectionState, NoneType]) = None
    RECEIVE_ID: set([int, NoneType]) = None
    RECEIVE_STATE: set([ConnectionState, NoneType]) = None

    def write_packet(self):
        raise Exception("Not implemented!")

    @classmethod
    def read_packet(cls, buffer: bytes):
        raise Exception("Not implemented!")

    def __repr__(self):
        return repr(self.__dict__)


class HandshakePacket(Packet):
    SEND_ID = 0
    SEND_STATE = ConnectionState.HANDSHAKE

    def __init__(self, action):
        self.action = action

    def write_packet(self):
        return struct.pack("<B", self.action.value)

    def __repr__(self):
        return f"<Handshake: action={self.action.name}>"

    class Action(Enum):
        PING = 1
        CONNECT = 2


packets.register(HandshakePacket)


class PingStatusPacket(Packet):
    RECEIVE_ID = 0
    RECEIVE_STATE = ConnectionState.PING

    def __init__(self, /, player_count: int, game_count: int, status_json: dict):
        self.player_count = player_count
        self.game_count = game_count
        self.status_json = status_json

    @classmethod
    def read_packet(cls, buffer: bytes):
        pc, gc, sj_len = struct.unpack_from("<III", buffer)
        return PingStatusPacket(
            player_count=pc,
            game_count=gc,
            status_json=json.loads(
                buffer[12:12 + sj_len],
                encoding="utf-8"
            )
        )


packets.register(PingStatusPacket)


class PingPongPacket(Packet):
    SEND_ID = 1
    SEND_STATE = ConnectionState.PING
    RECEIVE_ID = 1
    RECEIVE_STATE = ConnectionState.PING

    def __init__(self, random: int = None):
        if random is None:
            random = randint(0, 0xff_ff_ff_ff_ff_ff_ff_ff)
        assert random in range(0, 0xff_ff_ff_ff_ff_ff_ff_ff + 1)
        self.random = random

    def write_packet(self):
        return struct.pack("<Q", self.random)

    @classmethod
    def read_packet(self, buffer):
        random, = struct.unpack("<Q", buffer)
        return PingPongPacket(random)


packets.register(PingPongPacket)


class RequestEncryption(Packet):
    RECEIVE_ID = 0
    RECEIVE_STATE = ConnectionState.ENCRYPT

    def __init__(self, public_key, verify: bytes):
        self.public_key = public_key
        self.verify = verify
        print(repr(self))

    def create_response(self):
        response = EncryptionResponse(self.verify)
        secret = response.secret
        response.encrypt(self.public_key)
        return (response, secret)

    @classmethod
    def read_packet(self, buffer: bytes):
        l, = struct.unpack_from("<I", buffer)
        raw_pkey = buffer[4:(pos := 4 + l)]
        l, = struct.unpack_from("<I", buffer, pos)
        verify = buffer[pos + 4:pos + 4 + l]
        public_key = load_pem_public_key(raw_pkey, backends.default_backend())

        print(public_key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.PKCS1
        ).decode("utf-8"))

        return RequestEncryption(public_key, verify)


packets.register(RequestEncryption)


class EncryptionResponse(Packet):
    SEND_ID = 0
    SEND_STATE = ConnectionState.ENCRYPT

    def __init__(self, verify: bytes, secret=None):
        self.verify = verify
        if secret is None:
            secret = token_bytes(128)
        self.secret = secret
        print(repr(self))

    def encrypt(self, public_key):
        self.verify = self._encrypt(public_key, self.verify)
        self.secret = self._encrypt(public_key, self.secret)

    def _encrypt(self, public_key, data):
        return public_key.encrypt(
            data,
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    def write_packet(self):
        buffer = struct.pack("<I", len(self.verify))
        buffer += self.verify
        buffer += struct.pack("<I", len(self.secret))
        buffer += self.secret
        return buffer


packets.register(EncryptionResponse)


class EncryptionSuccess(Packet):
    RECEIVE_ID = 1
    RECEIVE_STATE = ConnectionState.ENCRYPT

    def __init__(self):
        pass

    def read_packet(self, buffer: bytes):
        check = struct.unpack("<I", buffer)
        assert check == 0xDEADBEEF
        return EncryptionSuccess()


packets.register(EncryptionSuccess)
