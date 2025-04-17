import pathlib
import tempfile

from menubox.hashome import Home


async def test_home():
    root = pathlib.Path(tempfile.mkdtemp())
    root2 = pathlib.Path(tempfile.mkdtemp())

    home1 = Home(root)
    assert Home(home1) is home1

    home2 = Home(str(root2))
    assert home2 is not home1
