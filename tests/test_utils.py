import pathlib

import pytest

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
