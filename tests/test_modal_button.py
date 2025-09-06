import asyncio
from typing import Self, cast, override

import ipywidgets as ipw

import menubox as mb
from menubox.modalbox import Modalbox
from menubox.trait_factory import TF


class PMBB(mb.MenuboxVT):
    task_button_run = TF.Future()
    task_update = TF.Future()
    count = TF.InstanceHP(klass=ipw.FloatText)
    slider = TF.InstanceHP(klass=ipw.IntSlider)
    box_extra = TF.HBox(cast(Self, 0)).hooks(set_children=lambda p: (p.count,))
    box_mb2 = TF.VBox()
    mb1 = TF.Modalbox(cast(Self, 0), obj=lambda p: p.box_extra, title="mb1 open")
    mb2 = TF.Modalbox(
        cast(Self, 0),
        obj=lambda p: p.get_mb2_widgets(),
        box=lambda p: p.box_mb2,
        title="mb2 open",
        header_children=lambda p: p.slider,
        button_expand_description="mb2",
        expand=True,
    )
    mb1_change_count = 0

    value_traits = mb.NameTuple("mb1.expanded")

    async def init_async(self):
        self.header_children = ("mb1", "mb2")
        self.views = {"Main": "box_mb2"}

    @override
    def on_change(self, change: mb.ChangeType):
        match change["owner"]:
            case self.mb1:
                if change["name"] == "expanded":
                    self.mb1_change_count += 1

    def get_mb2_widgets(self):
        return None, self.count


async def test_modal_button():
    obj = PMBB()
    assert isinstance(obj.mb1, Modalbox)
    assert obj.mb1_change_count == 0
    obj.mb1.expand()
    assert obj.mb1.expanded
    assert obj.mb1_change_count == 1
    assert obj.mb1.button_expand.disabled
    assert not obj.mb1.button_collapse.disabled
    obj.mb1.collapse()
    assert not obj.mb1.expanded
    assert obj.mb1_change_count == 2
    assert not obj.mb1.button_expand.disabled

    assert obj.mb2  # instantiate mb2
    await asyncio.sleep(0.2)
    assert obj.mb2.expanded, "expand=True"
    assert obj.mb2.button_expand.description == "mb2"
