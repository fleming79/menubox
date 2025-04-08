import anyio
import ipywidgets as ipw
import pytest

import menubox as mb
from menubox import trait_factory as tf
from menubox.menubox import MenuboxWrapper


class TestMenubox:
    async def test_menubox_basic_view_loading(self):
        wa, wb = ipw.HTML("A"), ipw.HTML("B")
        m = mb.Menubox(views={"a": wa, "b": wb})
        assert m.view == "a", "autoload selects first view"
        await m.wait_tasks()
        assert m.center is wa
        m.load_view(None)
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
        assert m.center is wb

    async def test_menubox_toggle_views(self):
        wa, wb = ipw.HTML("A"), ipw.HTML("B")
        m = mb.Menubox(views={"a": wa, "b": wb})
        assert not m._trait_values.get("button_toggleview")
        m.toggleviews = ("a", "b")
        assert m.button_toggleview, "Enabled automatically"
        await m.wait_tasks()
        assert m.header
        assert m.button_toggleview in m.header.children, "Should be added"
        assert m.view == "a"
        m.button_toggleview.click()
        assert m.view == "b"
        m.button_toggleview.click()
        assert m.view == "a"

    async def test_menubox_menu_views(self):
        wa, wb = ipw.HTML("A"), ipw.HTML("B")
        m = mb.Menubox(views={"a": wa, "b": wb})
        assert not m._trait_values.get("button_menu")
        m.menuviews = ("b",)
        assert m.button_menu, "Setting menuviews should enable the button"
        m.button_menu.click()
        await m.wait_tasks()
        assert m.box_menu
        assert m.button_menu_minimize in m.box_menu.children
        assert len(m.box_menu.children) == 2, "expected:button_menu_minimize, button_load_view"
        assert isinstance(m.box_menu.children[1], ipw.Button)
        assert m.box_menu.children[1].description == "b"
        m.box_menu.children[1].click()

    async def test_menubox_title_and_help(self):
        wa, wb = ipw.HTML("A"), ipw.HTML("B")
        m = mb.Menubox(views={"a": wa, "b": wb})
        m.title_description = "M"
        m.enable_widget("button_help")
        assert m.button_help
        await m.wait_tasks()
        m.refresh_view()
        m.mb_refresh()

    async def test_menubox_minimized_and_tuple_views(self):
        wa, wb = ipw.HTML("A"), ipw.HTML("B")
        m = mb.Menubox(views={"a": wa, "b": wb})
        await m.load_view("Minimized", reload=True)

        assert m.view == m._MINIMIZED
        m.maximize()
        m.views = {"A tuple": (ipw.HTML("Item1"), ipw.HTML("Item2"))}
        await m.load_view("A tuple", reload=True)

    async def test_menubox_shuffle_buttons(self):
        wa, wb = ipw.HTML("A"), ipw.HTML("B")
        m = mb.Menubox(views={"a": wa, "b": wb})
        m.shuffle_button_views = {"d": lambda: ipw.HTML("new")}
        assert "_shuffle_buttons" not in m.header_children
        m.load_view()
        await m.wait_tasks()
        assert m.shuffle_buttons
        m.shuffle_buttons[0].click()  # type: ignore # shuffle button for views 'd'
        await m.wait_tasks()

    async def test_menubox_view_setting(self):
        m2 = mb.Menubox()
        m2.views = {"m2": ipw.HTML("A"), "b": ipw.HTML("B")}
        await m2.load_view("b", reload=True)

        assert m2.view == "b"
        # Can also load views by setting the trait. It will be scheduled to load
        m2.view = "m2"
        # assert m2.view == "b", "load_view is debounced, retains the current view until loaded"
        await m2.wait_tasks()
        assert m2.view == "m2"

        m2.title_description = "M2"

        m2.tabviews = "m2", "b"
        await m2.wait_tasks()
        assert len(m2.tab_buttons) == 2

        await m2.wait_tasks()

    async def test_menubox_shuffle_box_integration(self):
        m2 = mb.Menubox()
        m2.views = {"m2": ipw.HTML("A"), "b": ipw.HTML("B")}
        m3 = mb.Menubox(title_description="m3", view=m2._MINIMIZED)
        await m3.wait_tasks()
        assert m3.view == m2._MINIMIZED
        await m3.wait_tasks()
        await m2.load_view(None, reload=True)
        assert m2.view is None, "load no view"
        m3.enable_widget("box_shuffle")
        abox = m3.box_shuffle
        assert abox
        m3.put_obj_in_box_shuffle(m2)
        await m2.wait_tasks()
        assert m2.view == m2.viewlist[0], "should have loaded first view."
        assert m2 in abox.children, "should be added without wrapper"
        assert m2.showbox is abox, "m2 should add itself to box_shuffle"
        assert m2.button_promote
        m2.set_trait("showbox", None)
        assert abox.comm, "Removing showbox should not close the box"
        assert m2 not in abox.children, "should be removed"

    async def test_menubox_shuffle_box_multiple_items(self):
        m2 = mb.Menubox()
        m2.views = {"m2": ipw.HTML("A"), "b": ipw.HTML("B")}
        m3 = mb.Menubox(title_description="m3", view=m2._MINIMIZED)
        await m3.wait_tasks()
        m3.enable_widget("box_shuffle")
        for i in range(3):
            m3.put_obj_in_box_shuffle(ipw.HTML(f"{i}"))

    async def test_menubox_shuffle_box_wrapping(self):
        m2 = mb.Menubox()
        m2.views = {"m2": ipw.HTML("A"), "b": ipw.HTML("B")}
        m3 = mb.Menubox(title_description="m3", view=m2._MINIMIZED)
        await m3.wait_tasks()
        m3.enable_widget("box_shuffle")
        abox = m3.box_shuffle
        assert abox
        b = ipw.Button(description="Not a Menubox")
        wrapper = m3.put_obj_in_box_shuffle(b)
        assert wrapper.view == "widget"
        assert wrapper.widget is b
        assert b not in abox.children, "should be added with wrapper"
        assert wrapper in abox.children
        assert m3.obj_in_box_shuffle(b) is wrapper
        assert wrapper is m3.obj_in_box_shuffle(b), "should be able to find it."
        assert m3.obj_in_box_shuffle(m3) is None
        await wrapper.wait_tasks()
        assert b is wrapper.widget
        assert wrapper.view == "widget"

    async def test_menubox_enable_menu_button(self):
        m2 = mb.Menubox()
        m2.views = {"m2": ipw.HTML("A"), "b": ipw.HTML("B")}
        m2.enable_widget("button_menu")
        assert m2.button_menu

    async def test_menubox_default_view(self):
        wa = ipw.HTML("A")
        mb.Menubox.DEFAULT_VIEW = "a"
        m = mb.Menubox(views={"a": wa, "b": ipw.HTML("B")})
        assert m.view == "a"
        mb.Menubox.DEFAULT_VIEW = mb.defaults.NO_DEFAULT

    async def test_menubox_close(self):
        m = mb.Menubox()
        m.close()
        assert m.closed

        class Alive(mb.Menubox):
            KEEP_ALIVE = True

        m = Alive()
        m.close()
        assert not m.closed
        m.close(force=True)
        assert m.closed

    async def test_menubox_view_validation(self):
        m = mb.Menubox()
        with pytest.raises(IndexError):
            m.view = "invalid_view"

        with pytest.raises(NameError):
            m.views = {"Minimized": ipw.HTML()}

    async def test_menubox_viewlist_validation(self):
        m = mb.Menubox(views={"a": ipw.HTML("A"), "b": ipw.HTML("B")})
        m.viewlist = ("a", "b", "c")
        assert m.viewlist == ("a", "b")

    async def test_menubox_enable_disable_widget(self):
        m = mb.Menubox()
        m.enable_widget("button_promote", {"description": "test"})
        assert m.button_promote
        assert m.button_promote.description == "test"
        m.disable_widget("button_promote")
        assert m.button_promote is None

    async def test_menubox_show_hide(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        assert m.view == "a"
        m.hide()
        assert m.view is None
        m.unhide()
        assert m.view == "a"

    async def test_menubox_get_center(self):
        wa = ipw.HTML("A")
        m = mb.Menubox(views={"a": wa})
        view, center = await m.get_center("a")
        assert view == "a"
        assert center is wa

    async def test_menubox_mb_refresh(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        await m.mb_refresh()
        # Test should be run in debug mode which should also add the header
        assert m.children == (m.header, m.box_center)

    async def test_menubox_update_header(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")}, viewlist=())
        m.header_children = ("html_title",)
        await m.wait_tasks()
        m._update_header()

    async def test_menubox_get_menu_widgets(self):
        m = mb.Menubox(views={"a": ipw.HTML("A"), "b": ipw.HTML("B")})
        m.menuviews = ("a", "b")
        widgets = m.get_menu_widgets()
        assert len(widgets) == 2
        assert isinstance(widgets[0], ipw.Button)

    async def test_menubox_menu_open_close(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        m.enable_widget("button_menu")
        m.menu_open()
        assert m.box_menu
        m.menu_close()
        assert m.box_menu.children == (m.button_menu,)

    async def test_menubox_mb_configure(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        await m.mb_configure()
        assert m._mb_configured

    async def test_menubox_get_help_widget(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        assert m.view == "a"
        await m.wait_tasks()
        assert len(m.children) == 2
        m.show_help = True
        await m.wait_tasks()
        assert len(m.children) == 3

    async def test_menubox_update_title(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        m.title_description = "test"
        m.update_title()

    async def test_menubox_get_button_loadview(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        button = m.get_button_loadview("a")
        assert isinstance(button, ipw.Button)
        with pytest.raises(ValueError, match="A view name is required.*"):
            m.get_button_loadview(None)
        with pytest.raises(KeyError):
            m.get_button_loadview("invalid")

    async def test_menubox_update_views_onchange(self):
        m = mb.Menubox(views={"a": ipw.HTML("A"), "b": ipw.HTML("B")})
        m._update_views_onchange()

    async def test_menubox_update_tab_buttons(self):
        m = mb.Menubox(views={"a": ipw.HTML("A"), "b": ipw.HTML("B")})
        m.tabviews = ("a", "b")
        m._update_tab_buttons()
        assert len(m.tab_buttons) == 2

    async def test_menubox_update_shuffle_buttons(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        m.shuffle_button_views = {"a": ipw.HTML("A")}
        m._update_shuffle_buttons()
        assert len(m.shuffle_buttons) == 1

    async def test_menubox_onchange_showbox(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        box = ipw.Box()
        m.set_trait("showbox", box)
        assert m in box.children
        m.set_trait("showbox", None)
        assert m not in box.children
        m.set_trait("showbox", box)
        m.close()
        assert m not in box.children

    @pytest.mark.parametrize(
        "name",
        [
            "button_menu",
            "button_promote",
            "button_demote",
            "button_minimize",
            "button_maximize",
            "button_help",
            "button_activate",
            "button_exit",
            "button_close",
        ],
    )
    async def test_menubox_button_clicked(self, name: str):
        showbox = ipw.Box(children=[ipw.Label("item")])
        m = mb.Menubox(views={"a": ipw.HTML("A"), "b": ipw.HTML("B")})
        m.toggleviews = ("a", "b")
        m.set_trait("showbox", showbox)
        m.enable_widget(name)
        await m.wait_tasks()
        b = getattr(m, name)
        assert isinstance(b, ipw.Button)
        assert b.comm
        assert m.header
        if name not in ["button_menu", "button_maximize"]:
            assert b in m.header.children
        b.click()
        await m.wait_tasks()
        match name:
            case "button_menu":
                assert m.box_menu
                assert m.button_menu_minimize
                assert b not in m.box_menu.children
                m.button_menu_minimize.click()
                assert b in m.box_menu.children
            case "button_promote":
                assert m is showbox.children[0]
            case "button_demote":
                assert m is showbox.children[0]
            case "button_minimize":
                assert m.view == m._MINIMIZED
            case "button_maximize":
                m.load_view(m._MINIMIZED)
                b.click()
                assert m.view == "a"
            case "button_help":
                assert len(m.children) == 3  # type: ignore
                b.click()
                await m.wait_tasks()
                assert len(m.children) == 2  # type: ignore
            case "button_activate":
                pass
            case "button_exit":
                assert m not in showbox.children
            case "button_close":
                assert m not in showbox.children
                assert m.closed
        m.disable_widget(name)
        assert not b.comm

    async def test_menubox_shuffle_button_on_click(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        m.enable_widget("box_shuffle")
        assert m.box_shuffle
        m.shuffle_button_views = {"a": ipw.HTML("A")}
        m.get_shuffle_button("a")
        for b in m.shuffle_buttons:
            m._shuffle_button_on_click(b)
        assert len(m.box_shuffle.children) == 1

    async def test_menubox_hide_unhide_shuffle_button(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        m.shuffle_button_views = {"a": ipw.HTML("A")}
        m.get_shuffle_button("a")
        m.hide_unhide_shuffle_button("a")
        await m.wait_tasks()
        m.hide_unhide_shuffle_button("a", hide=False)

    async def test_menubox_get_shuffle_button(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        m.shuffle_button_views = {"a": ipw.HTML("A")}
        button = m.get_shuffle_button("a")
        assert isinstance(button, ipw.Button)

    async def test_menubox_obj_in_box_shuffle(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        m.enable_widget("box_shuffle")
        widget = ipw.HTML()
        m.put_obj_in_box_shuffle(widget)
        assert m.obj_in_box_shuffle(widget)

    async def test_menubox_load_shuffle_item(self):
        class MenuboxA(mb.Menubox):
            a = tf.HTML(value="a")

        m = MenuboxA(views={"a": ipw.HTML("A")})
        m.enable_widget("box_shuffle")
        m.load_shuffle_item("a")
        assert m.box_shuffle
        assert len(m.box_shuffle.children) == 1
        w = ipw.HTML("W")
        m.load_shuffle_item(w)
        assert len(m.box_shuffle.children) == 2

    async def test_menubox_put_obj_in_box_shuffle(self):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        m2 = mb.Menubox(views={"a": ipw.HTML("m2")})
        m.enable_widget("box_shuffle")
        assert m.box_shuffle
        widget = ipw.HTML()
        m.put_obj_in_box_shuffle(widget)
        assert m.box_shuffle.children
        wrapper = m.box_shuffle.children[0]
        m.put_obj_in_box_shuffle(m2, position="start")
        assert m.box_shuffle.children == (m2, wrapper)
        m.put_obj_in_box_shuffle(m2)
        assert m.box_shuffle.children == (wrapper, m2)
        m2.set_trait("showbox", m.box_shuffle)
        m.put_obj_in_box_shuffle(m2, ensure_wrapped=True, alt_name="test")
        assert m2.showbox is None
        assert len(m.box_shuffle.children) == 2
        wrapper2 = m.box_shuffle.children[1]
        assert isinstance(wrapper2, MenuboxWrapper)
        assert wrapper2.widget is m2
        for w in (m2, widget):
            w.close()
            with pytest.raises(RuntimeError):
                m.put_obj_in_box_shuffle(w)
        with pytest.raises(RuntimeError):
            m.put_obj_in_box_shuffle(m)
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        with pytest.raises(TypeError):
            m.put_obj_in_box_shuffle(1)  # type: ignore

    async def test_menubox_activate_deactivate(self, mocker):
        m = mb.Menubox(views={"a": ipw.HTML("A")}, view=None)
        assert m.view is None
        cb = mocker.patch.object(m, "add_to_shell")
        await m.activate()
        assert cb.call_count == 1
        assert cb.await_count == 1
        assert m.view == "a"
        m.deactivate()
        assert m.view is None

    async def test_menubox_show_in_dialog(self, mocker):
        m = mb.Menubox(views={"a": ipw.HTML("A")})
        cb = mocker.patch.object(m.app.dialog, "show_dialog")
        await m.show_in_dialog("test")
        assert cb.call_count == 1
        assert cb.await_count == 1
