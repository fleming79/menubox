import logging
import pathlib
import tempfile
from typing import Any, override

import ipywidgets as ipw
import pytest
import traitlets

import menubox.hasparent as mhp
import menubox.trait_types as tt
from menubox import log, mb_async
from menubox.repository import Repository

match = "This exception is intentional"


class HP(mhp.HasParent):
    parent_dlink = tt.NameTuple("a_dlink", "a_dlink2")
    parent_link = tt.NameTuple("a_link", "a_link2")

    somelist = tt.TypedTuple(traitlets.Instance(ipw.Text))
    a_link = traitlets.Int(0)
    a_dlink = traitlets.Float(0)
    a_link2 = traitlets.Instance(ipw.FloatText, ())
    a_dlink2 = traitlets.Instance(ipw.FloatText, ())
    caught_errors = traitlets.Int()

    @log.log_exceptions
    def a_func(self, raise_error=False):
        if raise_error:
            raise ValueError(match)
        return True

    async def a_func_async(self, raise_error=False):
        if raise_error:
            raise ValueError(match)
        return True

    @override
    def on_error(self, error: Exception, msg: str, obj: Any = None):
        self.caught_errors += 1


class TestHasParent:
    async def test_has_parent_setup(self):
        hp = HP()
        hp.somelist = (ipw.Text(description="in list", value="some value"),)

        obj = hp.somelist[0]
        assert isinstance(obj, ipw.Text)

        assert isinstance(hp.log, logging.Logger | logging.LoggerAdapter)

        parent = HP(a_link=2, a_dlink=4)

        hp.parent = parent

        assert len(hp._hp_reg_parent_link) == 2
        assert len(hp._hp_reg_parent_dlink) == 2

    async def test_has_parent_linking(self):
        hp = HP()
        parent = HP(a_link=2, a_dlink=4)
        hp.parent = parent

        assert hp.a_link == 2
        assert hp.a_dlink == 4

        hp.a_link = 3
        assert parent.a_link == 3

        parent.a_link = 1
        assert hp.a_link == 1

        hp.a_dlink = 5
        assert parent.a_dlink == 4

        parent.a_dlink = 6
        assert hp.a_dlink == 6

        hp.parent_dlink = ()
        parent.a_dlink = 4
        assert hp.a_dlink == 6, "Not linked so shouldn't change"
        hp.parent_dlink = ("a_dlink", "a_dlink2")
        assert hp.a_dlink == 4, "Should update when dlinked"

        hp.parent_link = ()
        hp.a_link = 5
        assert parent.a_link == 1
        parent.a_link = 2
        assert hp.a_link == 5
        hp.parent_link = ("a_link", "a_link2")
        assert hp.a_link == 2

        parent.a_dlink2.value = 1.3
        assert hp.a_dlink2 is not parent.a_dlink2
        assert hp.a_dlink2.value == 1.3, "Should also dlink widget values not the widget"

        hp.a_link2.value = 0.98
        assert hp.a_link2 is not parent.a_link2
        assert hp.a_link2.value == 0.98, "Should also link widget values not the widget"

    async def test_has_parent_cleanup(self):
        hp = HP()
        parent = HP(a_link=2, a_dlink=4)
        hp.parent = parent

        hp.parent = None
        parent.a_link = parent.a_dlink = 0
        parent.a_link2.value = parent.a_dlink2.value = 0.2

        assert not hp._hp_reg_parent_dlink
        assert not hp._hp_reg_parent_link

        assert parent.a_link != hp.a_link
        assert parent.a_dlink != hp.a_dlink
        assert parent.a_link2.value != hp.a_link2.value
        assert parent.a_dlink2.value != hp.a_dlink2.value

    async def test_hasparent_linking_equality(self):
        # Linking checks for equality.
        # Dataframes need special consideration
        hp = HP()
        hp2 = HP()
        parent = HP(a_link=2, a_dlink=4)

        hp2.parent = hp

        class HPsubclass(HP):
            SINGLE_BY = ("name",)

        with pytest.raises(KeyError):
            hps = HPsubclass(a_link=hp.a_link + 1, a_dlink=hp.a_dlink + 2)

        hps = HPsubclass(a_link=hp.a_link + 1, a_dlink=hp.a_dlink + 2, name="hps")

        assert hps.a_link != hp.a_link
        assert hps.a_dlink != hp.a_dlink

        hp.parent = parent

        assert not hps.parent
        hps.parent = hp

        parent.a_link = 10
        parent.a_dlink = 20

        assert hps.a_link == parent.a_link
        assert hps.a_dlink == parent.a_dlink

        hps.a_link = 11
        hps.a_dlink = 21

        assert parent.a_link == hps.a_link == 11
        assert parent.a_dlink != hps.a_dlink
        assert hps.a_dlink == 21
        assert parent.a_dlink == 20

    async def test_hasparent_linking_functions(self):
        hp = HP()
        parent = HP(a_link=2, a_dlink=4)

        class HPsubclass(HP):
            SINGLE_BY = ("name",)

        hps = HPsubclass(a_link=hp.a_link + 1, a_dlink=hp.a_dlink + 2, name="hps")
        hp.parent = parent
        hps.parent = hp

        hps.link((parent, "a_link"), (hps, "a_dlink"))
        hps.dlink((parent, "a_dlink"), (parent, "a_dlink"))

        hps.link((parent, "a_link"), (hps, "a_dlink"), connect=False)
        hps.dlink((parent, "a_dlink"), (parent, "a_dlink"), connect=False)

        hps.link((parent, "a_link"), (hps, "a_dlink"))
        hps.dlink((parent, "a_dlink"), (parent, "a_dlink"))

        hps.close()

    async def test_hasparent_exceptions(self):
        hp = HP()
        assert hp.a_func() is True
        assert await hp.a_func_async() is True

        with pytest.raises(ValueError, match=match):
            hp.a_func(True)
        assert hp.caught_errors == 1
        with pytest.raises(ValueError, match=match):
            await mb_async.run_async(hp.a_func_async(True), obj=hp)

        assert hp.caught_errors == 2

    async def test_hasparent_cleanup_exceptions(self):
        hp = HP()

        class HPsubclass(HP):
            SINGLE_BY = ("name",)

        hps2 = HPsubclass(a_link=hp.a_link + 3, a_dlink=hp.a_dlink + 4, parent=hp, name="hbs2")
        hps3 = HPsubclass(a_link=hp.a_link + 5, a_dlink=hp.a_dlink + 5, parent=hp, name="hps3")

        # The exception
        with pytest.raises(Exception, match=match):
            await hp.a_func_async(True)

        hp.close()

        assert hps2.closed
        assert hps3.closed


async def test_home():
    root = pathlib.Path(tempfile.mkdtemp())
    root2 = pathlib.Path(tempfile.mkdtemp())

    home1 = mhp.Home(str(root))
    assert home1.repository.home is home1
    assert home1.repository.url.value == root.as_posix()
    assert mhp.Home(str(root)) is home1

    home2 = mhp.Home(str(root2))
    assert home2 is not home1

    repo1 = await home2.get_repository("repo")
    repo1a = await home2.get_repository("repo")
    assert repo1a is repo1, "Should return the same repository"
    repo1.close(force=True)
    assert repo1.closed
    repo1b = await home2.get_repository("repo")
    assert repo1b is not repo1, "Should have made a new version as the last was closed"

    assert isinstance(repo1, Repository)
    repo2 = await home1.get_repository("repo")
    assert repo1 is not repo2, "Repositories are unique by home and name"
