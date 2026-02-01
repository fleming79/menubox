import pathlib
from typing import Self, cast, override

import ipywidgets as ipw

import menubox as mb
from menubox.trait_factory import TF

templates_folder = pathlib.Path(__file__).parent.joinpath("templates")
assert templates_folder.exists()
mb.MenuboxVT.register_template_root_folder(templates_folder)


class MyNewObj(mb.HasHome, mb.MenuboxVT):
    SHOW_TEMPLATE_CONTROLS = True
    select_repository = TF.SelectRepository(cast("Self", 0))
    a_has_changed = False
    b_has_changed = False
    change_count = 0

    a = TF.InstanceHP(klass=ipw.FloatText)
    b = TF.InstanceHP(klass=ipw.FloatText)
    c = TF.InstanceHP(klass=ipw.FloatText)
    views = TF.ViewDict(cast("Self", 0), {"Main": ("description_viewer", "a", "b", "c")})
    value_traits_persist = mb.NameTuple[Self](lambda p: (*mb.MenuboxVT.value_traits, p.a, p.b, p.c))

    async def init_async(self):
        await super().init_async()
        self.add_value_traits("b")

    @override
    def on_change(self, change: mb.ChangeType):
        super().on_change(change)
        self.change_count = self.change_count + 1
        match change["owner"]:
            case self.a:
                self.a_has_changed = True
                self.b.value = self.a.value
            case self.b:
                self.b_has_changed = True
            case self.c:
                self.c_has_changed = True
            case _:
                match change["name"]:
                    case "c":
                        # Here we copy the value directly into the new widget
                        if change["old"]:
                            self.c.value = change["old"].value


async def test_menuboxvt(home: mb.Home):
    m = await MyNewObj(home=home)
    assert m.template_controls
    # Check that the values are registered and observed
    m.a.value = 12
    assert m.a_has_changed
    assert m.b_has_changed, "m.a sets m.b.value in `on_change`."
    await m
    m.a.value = 2
    assert m.b_has_changed

    m.c.value = 2.3
    assert m.c_has_changed

    m.c_has_changed = False
    c_old = m.c
    m.set_trait("c", ipw.FloatText(description="Replace c"))
    assert m.c is not c_old, "Widget gets replaced"
    assert m.c_has_changed, "Copying the value 'manually' to the new widget in on_change"
    assert m.c.value == 2.3, "'Manually' copied value."

    m.template_controls.expand()
    await m.template_controls.wait_tasks()
    await m
    assert len(m._sw_template.options) == 2, "Should locate template files"

    # Test load json template
    m._sw_template.index = 0
    m._button_load_template.click()
    await m.wait_tasks()
    assert m.a.value == 12.3, "From json template"
    assert m.c.value == 99, "From json template"

    # Test load yaml template
    m._sw_template.index = 1
    m._button_load_template.click()
    await m.wait_tasks()
    assert m.a.value == 10, "From yaml template"
    assert m.c.value == 20, "From yaml template"

    assert m._button_template_info

    await m.load_view(m.CONFIGURE_VIEW)
    assert m.view == m.CONFIGURE_VIEW

    m.text_name.value = "renamed"
    assert m.name == "renamed"
    m.RENAMEABLE = False
    m.text_name.value = "renamed again"
    assert m.name == "renamed"
    assert m.text_name.value == "renamed"

    await m.load_view("Main")

    assert m.box_center
    await m
    assert m.description_viewer in m.box_center.children, 'From view "Main"'
