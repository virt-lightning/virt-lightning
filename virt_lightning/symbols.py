import locale
from enum import Enum, unique


@unique
class SymbolsUTF(Enum):
    CROSS = "✕"
    CHECKMARK = "✔"


@unique
class SymbolsDefault(Enum):
    CROSS = "-"
    CHECKMARK = "+"


def get_symbols():
    lang, encoding = locale.getdefaultlocale()

    if encoding and encoding == "UTF-8":
        return SymbolsUTF
    return SymbolsDefault
