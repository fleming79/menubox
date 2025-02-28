import tempfile

import pandas as pd
import traitlets

import menubox as mb
from menubox import trait_factory as tf
from menubox.persist import MenuboxPersist


class MBP(MenuboxPersist):
    _STASH_DEFAULTS = True
    SINGLE_VERSION = False
    new = traitlets.Unicode()
    a_widget = tf.Text(description="something", value="Using the value")
    just_a_widget = tf.Dropdown(description="just_a_widget", options=[1, 2, 3]).configure(
        dlink={
            "source": ("self", "df"),
            "target": "layout.visibility",
            "transform": lambda df: mb.utils.to_visibility(df.empty, invert=True),
        }
    )
    value_traits_persist = mb.NameTuple("new", "a_widget.value", "just_a_widget")
    dataframe_persist = mb.NameTuple("df")
    df = traitlets.Instance(pd.DataFrame, default_value=pd.DataFrame())

    def view_main_get(self):
        return ("just_a_widget",)


async def test_persist():
    root = tempfile.mkdtemp()
    mt = mb.Home(root)

    p = MBP(parent=None, home=mt.name, name="main")
    p.just_a_widget.value = 2
    p.df = pd.DataFrame({"a": [1, 2, 3], "b": [3, 2, 1]})

    d = p.to_dict(hastrait_value=False)
    assert d["just_a_widget"] is p.just_a_widget

    await p.button_save_persistence_data.start()

    for view in p.views:
        await p.load_view(view, reload=True)

    assert p.get_persistence_versions(p.home, p.name)

    assert p.to_dict() != p._DEFAULTS
    assert p._DEFAULTS
    p.value = p._DEFAULTS  # Restore default value
    assert p.to_dict() == p._DEFAULTS
    # loading persistence data back in

    assert p.just_a_widget.value != 2
    await p.load_persistence_data()
    assert p.just_a_widget.value == 2

    assert p.to_dict() == p.to_dict()
    assert p.df.equals(p.df)

    p.menu_load_index.expand()
    p.version_widget.value = 2
    assert p.version == 2
    p.just_a_widget.value = 3
    await p.button_save_persistence_data.start()
    assert 2 in p.sw_version_load.options
    p.sw_version_load.value = 1
    await p.wait_update_tasks()
    assert p.just_a_widget.value == 2, "From persist v1"
    p.sw_version_load.value = 2
    await p.wait_update_tasks()
    assert p.just_a_widget.value == 3, "From persist v2"
