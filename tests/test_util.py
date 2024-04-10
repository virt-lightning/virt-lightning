import pytest

from virt_lightning.util import strtobool


@pytest.mark.parametrize(
    "str_value,expected",
    [
        ("t", True),
        ("T", True),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("y", True),
        ("Y", True),
        ("yes", True),
        ("Yes", True),
        ("YES", True),
        ("1", True),
        ("f", False),
        ("F", False),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("n", False),
        ("N", False),
        ("no", False),
        ("No", False),
        ("NO", False),
        ("0", False),
        (" f ", False),
        ("  f  ", False),
        (" f\t", False),
        (" f\n", False),
        (" f\r\n", False),
        ("f\r\n", False),
        ("\tf\r\n", False),
    ],
)
def test_strtobool(str_value: str, expected: bool):
    assert strtobool(str_value) == expected


@pytest.mark.parametrize(
    "str_value",
    [
        "",
        " ",
        "\n",
        "\r\n",
        "\t",
        "some-other-value",
        "a",
    ],
)
def test_strtobool__value_error(str_value: str):
    with pytest.raises(ValueError):
        strtobool(str_value)


@pytest.mark.parametrize(
    "str_value",
    [
        None,
        123,
        3.5,
        [],
        ["t"],
        ["t", "f"],
        {},
        {"t": "f"},
        ((),),
        (("t"),),
    ],
)
def test_strtobool__type_error(str_value: str):
    with pytest.raises(TypeError):
        strtobool(str_value)
