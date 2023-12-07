def strtobool(value: str) -> bool:
    """Convert a range of string representations of a boolean to bool. Case insensitive.

    String values converted to;

    bool[True]: ('t', 'true', 'y', 'yes', '1')
    bool[False]: ('f', 'false', 'n', 'no', '0')

    Raises TypeError in case of non-string type and ValueError when provided an invalid
    input.

    """
    if not isinstance(value, str):
        raise TypeError(f"{type(value)} cannot be converted to boolean")

    p_value = value.strip("\n\r\t ").lower()
    if p_value in ("t", "true", "y", "yes", "1"):
        return True
    elif p_value in ("f", "false", "n", "no", "0"):
        return False
    else:
        raise ValueError(f"Cannot convert to boolean {value!r}")
