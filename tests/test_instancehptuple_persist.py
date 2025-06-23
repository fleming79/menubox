from typing import Self, cast

import traitlets

from menubox import ValueTraits
from menubox.instancehp_tuple import InstanceHPTuple
from menubox.trait_factory import TF
from menubox.trait_types import NameTuple


class VTTP(ValueTraits):
    a = TF.Str()
    b = TF.Int(0)
    value_traits = NameTuple("a", "b")


class HPP(ValueTraits):
    widgets = InstanceHPTuple(VTTP, co_=cast(Self, 0)).hooks(set_parent=True)
    changecount = TF.Int(0)
    value_traits_persist = NameTuple("widgets")

    @traitlets.observe("widgets")
    def observe_somelist(self, change):
        self.changecount += 1


async def test_persist():
    hp = HPP()
    assert hp.changecount == 0
    hp.set_trait("widgets", ({"a": "A", "b": 10}, VTTP(a="B", b=2)))
    assert hp.changecount == 1

    assert hp.widgets[0].a == "A"

    assert hp.widgets[0].b == 10

    assert hp.widgets[1].a == "B"
    assert hp.widgets[1].b == 2

    hp.widgets[0].a = "C"
    hp2 = HPP()
    hp2.value = hp.to_dict(hastrait_value=False)

    assert hp.widgets == hp2.widgets

    hp3 = HPP()
    hp3.set_trait("value", hp.to_json())
    assert hp3.widgets is not hp.widgets
    assert hp.to_json() == hp3.to_json()

    hp.to_dict()
