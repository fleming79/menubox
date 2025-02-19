import tempfile

import traitlets

from menubox import TypedInstanceTuple, ValueTraits
from menubox.trait_types import NameTuple

# ruff: noqa: PLR2004


class VTTP(ValueTraits):
    a = traitlets.Unicode()
    b = traitlets.CInt()
    value_traits = NameTuple("a", "b")


class HPP(ValueTraits):
    widgets = TypedInstanceTuple(traitlets.Instance(VTTP))
    changecount = traitlets.Int(0)
    value_traits_persist = NameTuple("widgets")

    @traitlets.observe("widgets")
    def observe_somelist(self, change):
        self.changecount += 1


async def test_persist():
    tmpdir = tempfile.mkdtemp()
    hp = HPP(home=tmpdir)
    assert hp.changecount == 0
    hp.set_trait("widgets", ({"a": "A", "b": 10}, VTTP(a="B", b=2, home=hp.home)))
    assert hp.changecount == 1

    assert hp.widgets[0].a == "A"

    assert hp.widgets[0].b == 10

    assert hp.widgets[1].a == "B"
    assert hp.widgets[1].b == 2

    hp.widgets[0].a = "C"
    hp2 = HPP(home=hp.home)
    hp2.value = hp.to_dict(hastrait_value=False)

    assert hp.widgets == hp2.widgets

    hp3 = HPP(home=hp.home)
    hp3.set_trait("value", hp.to_json())
    assert hp3.widgets is not hp.widgets
    assert hp.to_json() == hp3.to_json()

    hp.to_dict()
