import pytest
import traitlets

from menubox.filesystem import DefaultFilesystem, Filesystem
from menubox.hashome import HasHome, Home


async def test_home():
    home1 = Home("home1")
    assert Home(home1) is home1

    home2 = Home("home2")
    assert home2 is not home1

    assert isinstance(home1.filesystem, Filesystem)
    assert home1.filesystem.read_only
    assert home2.filesystem is not home1.filesystem

    assert DefaultFilesystem(home=home1) is home1.filesystem


async def test_has_home(home: Home):
    hh1 = HasHome(home=home)
    assert hh1.home is home
    with pytest.raises(traitlets.TraitError):
        hh1.home = home  # pyright: ignore[reportAttributeAccessIssue]
    hh2 = HasHome(parent=hh1)
    assert hh2.parent is hh1
