import pathlib
from typing import Literal

import pytest
import traitlets

from menubox import utils


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (("\\\\windows\\test", "abc"), "//windows/test/abc"),
        (("C:\\", "test"), "C:/test"),
        (("C:/test/myfolder", "a/", "b\\", None, "/"), "C:/test/myfolder/a/b"),
        ((pathlib.PureWindowsPath("C:\\"), "test"), "C:/test"),
    ],
)
def test_utils_joinpaths(paths: tuple[str, ...], expected: str):
    assert utils.joinpaths(*paths) == expected


@pytest.mark.parametrize(
    ("obj", "max_len", "suffix", "mode", "expected"),
    [
        ("hello world", 5, "...", "start", "hello..."),
        ("hello world", 5, "...", "end", "...world"),
        ("hello world", 20, "...", "start", "hello world"),
    ],
)
def test_limited_string(obj: str, max_len: int, suffix: str, mode: Literal["start", "end"], expected: str):
    assert utils.limited_string(obj, max_len, suffix, mode) == expected


class MockTraitletsObject(traitlets.HasTraits):
    value = traitlets.Int(0)


class MockObject:
    def __init__(self):
        self.a = MockTraitletsObject()
        self.b = 1
        self.c = None


mock_obj = MockObject()


@pytest.mark.parametrize(
    ("obj", "name", "default", "expected"),
    [
        (mock_obj, "a.value", None, 0),
        (mock_obj, "b", None, 1),
        (mock_obj, "c", None, None),
        (mock_obj, "d", "default", "default"),
        (mock_obj, "a", None, 0),
        (mock_obj, "a.not_existing", "default", "default"),
        (mock_obj, "c.value", None, None),
    ],
)
def test_getattr_nested(obj: MockObject, name: str, default: str, expected: str | MockTraitletsObject):
    assert utils.getattr_nested(obj, name, default) == expected


def test_getattr_nested_no_hastrait_value():
    assert utils.getattr_nested(mock_obj, "a", None, hastrait_value=False) == mock_obj.a


def test_getattr_nested_attribute_error():
    with pytest.raises(AttributeError):
        utils.getattr_nested(mock_obj, "d")
