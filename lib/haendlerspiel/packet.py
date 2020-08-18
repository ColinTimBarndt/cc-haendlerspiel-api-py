from enum import Enum
import struct


class Packet:
    SEND_ID = -1
    RECEIVE_ID = -1

    def write_packet(self):
        raise Exception("Not implemented!")

    @classmethod
    def read_packet(cls, buffer):
        raise Exception("Not implemented!")


class Handshake(Packet):
    SEND_ID = 0

    def __init__(self, action):
        self.action = action

    def write_packet(self):
        return struct.pack("<B", self.action.value)

    def __repr__(self):
        return f"<Handshake: action={self.action.name}>"


class HandshakeAction(Enum):
    PING = 1
    CONNECT = 2
