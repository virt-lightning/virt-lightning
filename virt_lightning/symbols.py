import locale
from enum import Enum, unique


@unique
class SymbolsUTF(Enum):
    CROSS = "✕"
    CHECKMARK = "✔"
    LIGHTNING = "⚡"


@unique
class SymbolsDefault(Enum):
    CROSS = "-"
    CHECKMARK = "+"
    LIGHTNING = ""

def get_symbols():
    lang, encoding = locale.getdefaultlocale()

    if encoding and encoding == "UTF-8":
        return SymbolsUTF
    return SymbolsDefault
