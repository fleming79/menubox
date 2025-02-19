import ipywidgets as ipw

import menubox as mb
from menubox import utils


async def test_menubox():
    # ruff: noqa: PLR2004
    wa, wb = ipw.HTML("A"), ipw.HTML("B")
    m = mb.MenuBox(views={"a": wa, "b": wb})
    assert m.task_load_view
    await m.task_load_view
    assert m.view == "a", "autoload selects first view"
    await m.load_view(None, reload=True)
    assert m.view is None, "load no view"
    m.load_view()
    await m.wait_tasks()
    assert m.view == "a", "should load first view"

    await m.load_view(None, reload=True)
    assert m.view is None, "load no view"
    m.load_view("b")
    m.load_view()
    await m.wait_tasks()
    assert m.view == "b", "loading first shouldn't override load in progress"
    assert not m._trait_values.get("button_toggleview")
    m.toggleviews = ("a", "b")
    assert m.button_toggleview, "Enabled automatically"
    await m.wait_tasks()
    assert m.button_toggleview in m.header.children, "Should be added"
    m.button_toggleview.click()
    assert not m.task_load_view
    await m.wait_tasks()  # Button task
    await m.wait_tasks()  # Load view task
    assert m.view == "a"
    assert not m._trait_values.get("button_menu")
    m.menuviews = ("b",)
    assert m.button_menu, "Setting menuviews should enable the button"
    m.button_menu.click()
    await m.wait_tasks()
    assert m.button_menu_minimize in m.box_menu.children
    assert len(m.box_menu.children) == 2, "expected:button_menu_minimize, button_load_view"
    assert isinstance(m.box_menu.children[1], ipw.Button)
    assert m.box_menu.children[1].description == "b"
    m.box_menu.children[1].click()
    m.title_description = "M"
    m.enable_widget("button_help")
    assert m.button_help
    await m.wait_tasks()
    m.refresh_view()
    m.mb_refresh()
    await m.load_view("Minimized", reload=True)

    assert m.view == m._MINIMIZED
    m.maximize()
    m.views = {"A tuple": (ipw.HTML("Item1"), ipw.HTML("Item2"))}
    await m.load_view("A tuple", reload=True)

    m.shuffle_button_views = {"d": lambda: ipw.HTML("new")}
    assert "_shuffle_buttons" not in m.header_children
    m.load_view()
    await m.wait_tasks()
    m.shuffle_buttons[0].click()  # type: ignore # shuffle button for views 'd'
    await m.wait_tasks()
    m2 = mb.MenuBox()
    m2.views = {"m2": ipw.HTML("A"), "b": ipw.HTML("B")}
    await m2.load_view("b", reload=True)

    assert m2.view == "b"
    # Can also load views by setting the trait. It will be scheduled to load
    m2.view = "m2"
    assert m2.view == "b", "load_view is debounced, retains the current view until loaded"
    await m2.wait_tasks()
    assert m2.view == "m2"

    m2.title_description = "M2"

    m2.tabviews = "m2", "b"
    await m2.wait_tasks()
    assert len(m2.tab_buttons) == 2

    await m2.wait_tasks()

    # See we can create and GC a menubox
    mbox = mb.MenuBox()
    del mbox

    m3 = mb.MenuBox(title_description="m3", view=m2._MINIMIZED)
    await m3.wait_tasks()
    assert m3.view == m2._MINIMIZED
    await m3.wait_tasks()
    await m2.load_view(None, reload=True)
    assert m2.view is None, "load no view"
    m3.enable_widget("box_shuffle")
    abox = m3.box_shuffle
    assert abox
    utils.show_obj_in_box(m2, abox)
    await m2.wait_tasks()
    assert m2.view is next(iter(m2.views)), "should have loaded first view."
    assert m2 in abox.children, "should be added without wrapper"
    assert m2.showbox is abox, "m2 should add itself to box_shuffle"
    assert m2.button_promote
    m2.set_trait("showbox", None)
    assert abox.comm, "Removing showbox should not close the box"
    assert m2 not in abox.children, "should be removed"
    for i in range(3):
        utils.show_obj_in_box(ipw.HTML(f"{i}"), abox)
    b = ipw.Button(description="Not a MenuBox")
    wrapper = utils.show_obj_in_box(b, abox)
    assert wrapper.task_load_view
    await wrapper.task_load_view
    assert wrapper.view == "WRAPPED"
    assert wrapper._center is b
    assert b not in abox.children, "should be added with wrapper"
    assert wrapper in abox.children
    assert wrapper is next(iter(abox.children)), "Show in box should add to top of list."
    assert utils.obj_is_in_box(b, abox) is wrapper
    assert wrapper is m3.obj_in_box_shuffle(b), "should be able to find it."
    assert m3.obj_in_box_shuffle(m3) is None
    await wrapper.wait_tasks()
    assert b is wrapper._center, "b should be the loaded 'view'"
    assert abox.children.index(wrapper) == 0
    wrapper.button_demote.click()
    await wrapper.wait_tasks()
    assert abox.children.index(wrapper) == 1
    wrapper.button_promote.click()
    await wrapper.wait_tasks()
    assert wrapper is next(iter(abox.children))
    wrapper.button_exit.click()
    await wrapper.wait_tasks()
    assert wrapper not in abox.children

    m2.enable_widget("button_menu")
    assert m2.button_menu
    m2.header_left_children = ("header_children",)  # causes RecursionError in get_wigets
