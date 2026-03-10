import sys
from enum import Enum, unique


@unique
class SymbolsUTF(Enum):
    CHECKMARK = "✔"
    COMPUTER = "💻"
    CROSS = "✕"
    CUSTOMS = "🛃"
    HOURGLASS = "⌛"
    LIGHTNING = "⚡"
    RIGHT_ARROW = "⇛"
    THUMBS_UP = "👍"
    TRASHBIN = "🗑"


class SymbolsDefault(Enum):
    CHECKMARK = "+"
    COMPUTER = "+"
    CROSS = "-"
    CUSTOMS = "+"
    HOURGLASS = "..."
    LIGHTNING = ""
    RIGHT_ARROW = "->"
    THUMBS_UP = "+"
    TRASHBIN = "x"


def get_symbols():
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() == "utf-8":
            return SymbolsUTF
    except AttributeError:
        # To handle cases where sys.stdout.encoding is None, like > /dev/null
        pass
    return SymbolsDefault
