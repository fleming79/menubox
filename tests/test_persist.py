from __future__ import annotations

from typing import Self, cast

import pandas as pd
import traitlets

import menubox as mb
from menubox import trait_factory as tf
from menubox.persist import MenuboxPersist, MenuboxPersistPool


class MBP(MenuboxPersist):
    _STASH_DEFAULTS = True
    SINGLE_VERSION = False
    new = traitlets.Unicode()
    a_widget = tf.Text(description="something", value="Using the value")
    just_a_widget = tf.Dropdown(cast(Self, None), description="just_a_widget", options=[1, 2, 3]).hooks(
        on_set=lambda c: c["parent"].dlink(
            src=(c["parent"], "df"),
            target=(c["obj"].layout, "visibility"),
            transform=lambda df: mb.utils.to_visibility(df.empty, invert=True),
        ),
    )
    value_traits_persist = mb.NameTuple(*MenuboxPersist.value_traits_persist, "new", "a_widget.value", "just_a_widget")
    dataframe_persist = mb.NameTuple("df")
    df = traitlets.Instance(pd.DataFrame, default_value=pd.DataFrame())

    def view_main_get(self):
        return ("just_a_widget",)


async def test_persist(home: mb.Home):
    p = MBP(parent=None, home=home, name="main")
    p.just_a_widget.value = 2
    p.df = pd.DataFrame({"a": [1, 2, 3], "b": [3, 2, 1]})

    d = p.to_dict(hastrait_value=False)
    assert d["just_a_widget"] is p.just_a_widget

    await p.button_save_persistence_data.start()

    for view in p.views:
        await p.load_view(view).activate()

    assert p.get_persistence_versions(p.filesystem, p.name)

    assert p.to_yaml() != p._DEFAULTS
    assert p._DEFAULTS
    p.value = p._DEFAULTS  # Restore default value
    assert p.to_yaml() == p._DEFAULTS
    # loading persistence data back in

    assert p.just_a_widget.value != 2
    await p.load_persistence_data()
    assert p.just_a_widget.value == 2

    assert p.to_dict() == p.to_dict()
    assert p.df.equals(p.df)
    assert p.menu_load_index
    p.menu_load_index.expand()

    # version_widget
    assert p.version_widget
    p.version_widget.value = 2
    assert p.task_loading_persistence_data
    await p.task_loading_persistence_data
    assert p.version == 2
    await p.wait_update_tasks()
    p.just_a_widget.value = 3
    await p.button_save_persistence_data.start()

    # sw_version_load
    assert 2 in p.sw_version_load.options
    p.sw_version_load.value = 1
    assert p.task_loading_persistence_data
    await p.task_loading_persistence_data
    assert p.just_a_widget.value == 2, "From persist v1"
    p.sw_version_load.value = 2
    await p.wait_update_tasks()
    assert p.just_a_widget.value == 3, "From persist v2"


class Numbers(MenuboxPersist):
    a = mb.TypedTuple(traitlets.CFloat(), default_value=range(100))
    value_traits_persist = mb.NameTuple("a")


async def test_menubox_persist_pool(home: mb.Home):
    mpp = MenuboxPersistPool(home=home, name="Shuffle", klass=Numbers)
    mpp.show()
    name = "my object"
    obj = mpp.get_obj(name)
    assert isinstance(obj, MenuboxPersist)
    assert len(mpp.pool) == 1
    assert mpp.box_shuffle
    assert obj.name == name
    assert mpp.get_obj(name) is obj
    await mpp.wait_tasks()
    mpp.obj_name.value = name
    await mpp.wait_tasks()
    assert not obj.versions
    await obj.button_save_persistence_data.start()
    assert obj.versions
    await mpp.wait_tasks()
