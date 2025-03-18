from __future__ import annotations

import pathlib
import tempfile

import ipywidgets as ipw
import traitlets

import menubox as mb
from menubox.persist import MenuboxPersist
from menubox.shuffle import ObjShuffle


class Numbers(MenuboxPersist):
    a = mb.TypedTuple(traitlets.CFloat(), default_value=range(100))
    value_traits_persist = mb.NameTuple("a")


class ObjNumberShuffle(ObjShuffle):
    obj_cls = traitlets.Type(Numbers)


async def test_shuffle():
    root = pathlib.Path(tempfile.mkdtemp())
    home = mb.Home(str(root))
    assert home.name == root.name
    assert root.as_posix() == home.repository.url.value

    shuffle = ObjNumberShuffle(home=home, name="Shuffle")
    assert shuffle.obj_cls

    await shuffle.load_view(reload=True)
    name = "my object"
    shuffle.sw_obj.value = name
    obj = await shuffle.button_show_obj.start()
    assert isinstance(obj, MenuboxPersist)
    assert len(shuffle.pool) == 1
    assert shuffle.box_shuffle
    assert obj in shuffle.box_shuffle.children
    assert obj.name == name
    assert shuffle.get_obj(name) is obj
    await shuffle.wait_tasks()
    shuffle.sw_obj.value = name
    await shuffle.wait_tasks()
    assert (obj, "versions") in shuffle._vt_tuple_reg["pool"].reg, "versions causes rescan"
    assert not obj.versions
    assert not shuffle.sw_version.options
    await obj.button_save_persistence_data.start()
    assert obj.versions
    await shuffle.wait_tasks()
    assert shuffle.sw_obj.value == name
    assert shuffle.sw_version.options
    shuffle.modal_info.expand()
    shuffle.sw_version.index = 0
    await shuffle.update_box_info()
    await shuffle.wait_tasks()
    assert shuffle.box_info.children
    assert isinstance(shuffle.box_info.children[0], ipw.HBox)
