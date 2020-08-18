from enum import Enum

class ConnectionState(Enum):
    HANDSHAKE = 0
    PING = 1
    ENCRYPT = 2
    LOGIN = 3
    JOINING = 4
    PLAYING = 5
