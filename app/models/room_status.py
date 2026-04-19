
from enum import Enum

class RoomStatus(str, Enum):
    waiting = "waiting"
    lobby = "lobby"
    running = "running"
    finished = "finished"
