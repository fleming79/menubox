from menubox.filesystem import Filesystem
from menubox.hashome import Home


async def test_home():
    home1 = Home("home1")
    assert Home(home1) is home1

    home2 = Home("home2")
    assert home2 is not home1

    assert isinstance(home1.filesystem, Filesystem)
    assert home1.filesystem.read_only
    assert home2.filesystem is not home1.filesystem
