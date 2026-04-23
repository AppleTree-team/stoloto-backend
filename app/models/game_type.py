from enum import Enum

class GameType(str, Enum):
    wheel = "wheel"
    aviator = "aviator"
    plinko = "plinko"
    minesweeper = "minesweeper"
