from __future__ import annotations

import asyncio
import contextlib
import re
import textwrap
import weakref
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar, Final, Generic, Literal, Self, Unpack, cast, overload, override

import docstring_to_markdown
import ipylab.shell
import ipylab.widgets
import traitlets
from ipylab import Panel, ShellConnection
from ipywidgets import widgets as ipw

import menubox as mb
from menubox import defaults, log, mb_async, utils
from menubox import trait_factory as tf
from menubox.css import CSScls
from menubox.defaults import H_FILL, NO_DEFAULT, V_FILL
from menubox.hasparent import HasParent, Parent
from menubox.trait_types import RP, ChangeType, ProposalType, ReadOnly, StrTuple

if TYPE_CHECKING:
    from ipylab.widgets import AddToShellType

    from menubox.instance import IHPChange

CLEANR = re.compile("<.*?>")


def cleanhtml(raw_html):
    "Remove basic html and &emsp;"
    return re.sub(CLEANR, "", raw_html).replace("&emsp;", "")


class Buttons(traitlets.TraitType[tuple[ipw.Button, ...], Iterable[ipw.Button]]):
    default_value = ()

    def validate(self, obj: Menubox, value):
        return tuple(v for v in value if isinstance(v, ipw.Button) and v._repr_keys)


class HTMLNoClose(ipw.HTML):
    def close(self):
        return


HTML_LOADING = HTMLNoClose("Loading ...")


class Menubox(HasParent, Panel, Generic[RP]):
    """An all-purpose widget intended to be subclassed for building gui's."""

    MINIMIZED: Final = "Minimized"
    RESERVED_VIEWNAMES: ClassVar[tuple[str | None, ...]] = (MINIMIZED,)
    DEFAULT_VIEW: ClassVar[str | None | defaults.NO_DEFAULT_TYPE] = None
    HELP_HEADER_TEMPLATE = "<h3>ℹ️ {self.__class__.__qualname__}</h3>\n\n"  # noqa: RUF001
    _setting_view = False
    _mb_configured = False
    _Menubox_init_complete = False
    # Traits
    parent = Parent[Self, RP]()
    show_help = tf.Bool()
    viewlist = StrTuple()
    toggleviews = StrTuple()
    menuviews = StrTuple()
    tabviews = StrTuple()
    css_classes = StrTuple(CSScls.Menubox, help="Class names to add when the view is not None.")
    views = tf.ViewDict(cast(Self, 0))
    shuffle_button_views: tf.InstanceHP[
        Self, dict[str, ipw.Widget | Menubox | str], dict[str, ipw.Widget | Menubox | str]
    ] = tf.Dict().configure(
        allow_none=False,
        read_only=False,
    )
    border = tf.Str().configure(read_only=False, allow_none=True, default_value=None)
    view = tf.Str(default=lambda _: None).configure(read_only=False, allow_none=True, default_value=None)
    view_previous = tf.Str(default=lambda _: None).configure(read_only=False, allow_none=True, default_value=None)
    title_description = tf.Str()
    title_description_tooltip = tf.Str()

    header_left_children = StrTuple("button_exit", "button_minimize", "box_menu", "button_toggleview")
    header_right_children = StrTuple(
        "button_help", "button_activate", "button_promote", "button_demote", "button_close"
    )
    header_children = StrTuple(
        "header_left_children", "html_title", "tab_buttons", "shuffle_buttons", "H_FILL", "header_right_children"
    )
    box_menu_open_children = StrTuple("button_menu_minimize", "get_menu_widgets")
    minimized_children = StrTuple("html_title", "header_right_children")

    loading_view: traitlets.Instance[defaults.NO_DEFAULT_TYPE | str | None] = traitlets.Any(
        default_value=NO_DEFAULT, read_only=True
    )  # type: ignore
    # Trait instances
    center: traitlets.TraitType[utils.GetWidgetsInputType, utils.GetWidgetsInputType] = traitlets.TraitType(
        read_only=True, allow_none=True
    )
    tab_buttons = Buttons(read_only=True)
    shuffle_buttons = Buttons(read_only=True)
    # Trait factory
    _view_buttons = tf.InstanceHP[Self, weakref.WeakSet[ipw.Button], ReadOnly](klass=weakref.WeakSet)
    _tab_buttons = tf.InstanceHP[Self, weakref.WeakSet[ipw.Button], ReadOnly](klass=weakref.WeakSet)
    task_load_view = tf.Task()
    html_title = tf.HTML_Title().configure(allow_none=True, read_only=True, load_default=False)
    out_help = tf.MarkdownOutput().hooks(add_css_class=(CSScls.resize_both, CSScls.nested_borderbox))

    # Buttons
    button_menu = tf.Button_menu(description="☰").configure(read_only=True, allow_none=True)
    button_toggleview = tf.Button_menu(description="➱").configure(allow_none=True, read_only=True, load_default=False)
    button_help = tf.Button_open(description="❔").configure(allow_none=True, read_only=True, load_default=False)
    button_close = tf.Button_dangerous(description="✗", tooltip="Close").configure(
        allow_none=True, read_only=True, load_default=False
    )
    button_minimize = tf.Button_open(description="🗕", tooltip="Minimize").configure(
        allow_none=True, read_only=True, load_default=False
    )
    button_maximize = tf.Button_open(description="🗖", tooltip="Restore").configure(
        allow_none=True, read_only=True, load_default=False
    )
    button_exit = tf.Button_open(description="⇡", tooltip="Leave showbox").configure(
        allow_none=True, read_only=True, load_default=False
    )
    button_promote = tf.Button_open(description="⇖", tooltip="Shift up / left").configure(
        allow_none=True, read_only=True, load_default=False
    )
    button_demote = tf.Button_open(description="⇘", tooltip="Shift down / right").configure(
        allow_none=True, load_default=False, read_only=True
    )
    button_menu_minimize = tf.Button_menu(description="↤", tooltip="Hide menu").configure(
        allow_none=True, read_only=True, load_default=False
    )
    button_activate = tf.Button_open(description="🐑", tooltip="Add to shell").configure(
        allow_none=True, read_only=True, load_default=False
    )

    # Boxes
    box_shuffle = tf.MenuboxShuffle().configure(allow_none=True, read_only=True)
    box_menu = tf.MenuboxMenu().configure(allow_none=True, read_only=True)
    showbox = (
        tf.InstanceHP(cast(Self, 0), klass=ipw.Box)
        .hooks(on_replace_close=False, remove_on_close=False, value_changed=lambda c: c["parent"]._onchange_showbox(c))
        .configure(allow_none=True, load_default=False, read_only=False)
    )
    header = tf.MenuboxHeader().configure(allow_none=True, read_only=True)
    box_center = tf.MenuboxCenter().configure(allow_none=True, read_only=True)
    _mb_refresh_traitnames = (
        "closed",
        "show_help",
        "html_title",
        "border",
        "name",
        "title",
        "title_description",
        "title_description_tooltip",
        "header",
        "header_left_children",
        "header_right_children",
        "header_children",
        "views",
        "viewlist",
        "toggleviews",
        "menuviews",
        "button_menu",
        "button_menu_minimize",
        "button_toggleview",
        "button_minimize",
        "button_maximize",
        "button_promote",
        "button_demote",
        "button_exit",
        "button_help",
        "button_close",
        "center",
        "remover",
        "tab_buttons",
        "shuffle_buttons",
        "shuffle_button_views",
        "tabviews",
    )

    @traitlets.default("title")
    def _default_title(self):
        return ipylab.widgets.Title(icon=mb.plugin_manager.hook.get_icon(obj=self))

    @property
    def _current_views(self):
        if not self.viewlist and self.views:
            self.viewlist = tuple(self.views)
        return (*self.viewlist, *self.RESERVED_VIEWNAMES, None)

    @property
    def view_active(self) -> bool:
        """Check if the view is currently active (not minimized).

        Returns:
            bool: True if the view is active, False otherwise.
        """
        return bool(self.view and self.view != self.MINIMIZED)

    def __init__(
        self,
        *,
        parent: RP = None,
        view=NO_DEFAULT,
        views: dict[str, utils.GetWidgetsInputType] | None = None,
        viewlist: Iterable[str] | None = None,
        tabviews: Iterable[str] | None = None,
        **kwargs,
    ):
        if self._Menubox_init_complete:
            return
        self._initial_view = view if view is not NO_DEFAULT else self.DEFAULT_VIEW
        if views:
            self.set_trait("views", views)
        if viewlist:
            self.set_trait("viewlist", viewlist)
        if tabviews:
            self.set_trait("tabviews", tabviews)
        self._Menubox_init_complete = True
        super().__init__(parent=parent, **kwargs)

    @override
    async def init_async(self):
        await super().init_async()
        if self._initial_view and not self.trait_has_value("loading_view"):
            self.load_view(self._initial_view)

    @traitlets.validate("views")
    def _vaildate_views(self, proposal: ProposalType):
        views = proposal["value"]
        for view in views:
            if view in self.RESERVED_VIEWNAMES:
                msg = f"{view=} is a reserved name!"
                raise NameError(msg)
        return views

    @traitlets.validate("view")
    def _vaidate_view(self, proposal: ProposalType):
        if proposal["value"] not in self._current_views:
            msg = f"View {proposal['value']!r} not in {self._current_views}"
            raise IndexError(msg)
        if self._setting_view:
            return proposal["value"]
        self.load_view(proposal["value"])
        return self.view

    @traitlets.validate("viewlist", "toggleviews", "tabviews", "menuviews")
    def _validate_viewlist_names(self, proposal: ProposalType):
        views = self.views if proposal["trait"].name == "viewlist" else self._current_views
        val = tuple(v for v in proposal["value"] if v and v in views)
        if proposal["trait"].name == "viewlist" and not val:
            return tuple(views)
        return val

    @traitlets.default("viewlist")
    def _default_viewlist(self):
        return tuple(self.views)

    def maximize(self) -> Self:
        if self.view_previous and self.view_previous not in (None, self.MINIMIZED):
            view = self.view_previous
        else:
            view = self._current_views[0]
        return self.load_view(view)

    def show(self) -> Self:
        """A non-agressive means to provide an interactive interface."""
        if self.view is None:
            self.maximize()
        return self

    def load_view(self, view: str | None | defaults.NO_DEFAULT_TYPE = NO_DEFAULT, reload=False) -> Self:
        """Loads a specified view, handling defaults, reloads, and preventing redundant loads.

        Args:
            view (str | None | defaults.NO_DEFAULT_TYPE, optional): The name of the view to load.
            If NO_DEFAULT or None, defaults to the current view or the first available view.
            Defaults to NO_DEFAULT.
            reload (bool, optional): If True, forces a reload of the view even if it's already loaded.
            Defaults to False.

        Returns:
            Task | None: Returns a Task object if a new view loading task is started.
            Returns None if the view is already loaded and reload is False.

        Raises:
            RuntimeError: If the specified view is not in the set of current views.
        """
        if self.closed:
            return self
        current = self._current_views
        if view is NO_DEFAULT:
            view = self.view
            if not view or view not in current:
                view = self.loading_view
                if view not in current:
                    view = self._current_views[0]
        elif view not in self._current_views:
            msg = f'{view=} is not a current view! Available views = "{self._current_views}"'
            raise RuntimeError(msg)
        if not reload:
            if self.task_load_view:
                if self.loading_view == view:
                    return self
            elif view == self.view:
                return self
        self._load_view(view)
        return self

    @mb_async.singular_task(handle="task_load_view", tasktype=mb_async.TaskType.update)
    async def _load_view(self, view: str | None):
        self.set_trait("loading_view", view)
        self.mb_refresh()
        if view and not self._mb_configured:
            await self.mb_configure()
        try:
            view, center = await self.get_center(view)
            self._setting_view = True
            self.view = view
            self._setting_view = False
            self.set_trait("center", center)
            self.log.debug("Loaded view: %s", view)
        finally:
            self.set_trait("loading_view", NO_DEFAULT)
        if view:
            for clsname in self.css_classes:
                self.add_class(clsname)
        else:
            for clsname in self.css_classes:
                self.remove_class(clsname)
        if view and view != self.view_previous:
            self.set_trait("view_previous", view)
        for b in self._view_buttons:
            (b.add_class if b.description == view else b.remove_class)(CSScls.button_active_view)
        self.menu_close()
        if self.button_menu:
            self.button_menu.tooltip = f"Show menu for {self.__class__.__qualname__}\nCurrent view: {view}"
        if self.button_toggleview and view in self.toggleviews:
            i = (self.toggleviews.index(view) + 1) % len(self.toggleviews)
            next_view = self.toggleviews[i]
            self.button_toggleview.tooltip = f"Current: {view}\nNext:{next_view}\nAvailable: {self.toggleviews}"
        return view

    async def get_center(self, view: str | None) -> tuple[str | None, utils.GetWidgetsInputType]:
        """Override this function to make view loading dynamic.

        **DO NOT CALL DIRECTLY**

        Args:
            view: The name of the view to get the center widget for.

        Returns:
            A tuple containing the name of the view and the center.
        """
        return view, self.views.get(view, None)  # type: ignore

    @mb_async.throttle(0.05)
    async def mb_refresh(self) -> None:
        """Refreshes the Menubox's display based on its current state.

        This method updates the Menubox's children widgets to reflect changes
        in the view, title, and header. It handles loading states, minimized
        views, and debug mode configurations.

        Returns:
            None
        """
        if not self._Menubox_init_complete or self.closed:
            return
        if mb.DEBUG_ENABLED:
            self.enable_ihp("button_activate")
        if self.task_load_view and self.loading_view:
            self.set_trait("children", (HTML_LOADING,))
            await asyncio.wait([self.task_load_view])
            self.mb_refresh()
            return
        if not self.view:
            self.set_trait("children", ())
            return
        self.update_title()
        self._update_header()
        if self.view == self.MINIMIZED:
            self.set_trait("children", (self.header,))
        else:
            center = (self.center,)
            if self.box_center:
                self.box_center.children = self.get_widgets(*center)
                center = (self.box_center,)
            if mb.DEBUG_ENABLED and not self.header:
                center = (self.button_activate, *center)
            if self.show_help:
                center = (self._get_help_widget, *center)
            self.set_trait("children", self.get_widgets(self.header, *center))
        if self.border is not None:
            self.layout.border = self.border if self.view else ""

    def _update_header(self):
        if self.view == self.MINIMIZED:
            self.enable_ihp("header")
            self.enable_ihp("button_maximize")
            assert self.header  # noqa: S101
            self.header.children = self.get_widgets(self.button_maximize, self.button_exit, *self.minimized_children)
        else:
            widgets = tuple(self.get_widgets(*self.header_children))
            if set(widgets).difference((H_FILL, V_FILL)):
                self.enable_ihp("header")
                assert self.header  # noqa: S101
                self.header.children = widgets
            else:
                self.disable_ihp("header")

    def refresh_view(self) -> Self:
        """Refreshes the view by reloading it.
        Returns:
            asyncio.Task[str | None]: An asynchronous task that reloads the view
            and returns either a string or None.
        """
        return self.load_view(reload=True)

    def get_menu_widgets(self):
        return tuple(self.get_button_loadview(v) for v in self.menuviews if v is not self.view)

    def menu_open(self):
        self.enable_ihp("button_menu_minimize")
        assert self.box_menu  # noqa: S101
        self.box_menu.children = tuple(self.get_widgets(*self.box_menu_open_children))

    def menu_close(self):
        if self.box_menu:
            self.box_menu.children = (self.button_menu,) if self.button_menu else ()

    async def mb_configure(self) -> None:
        """Configure this widget - called once only when loading the first view.

        This includes:
            - Enabling the maximize button if it exists or if the default view is minimized.
            - Enabling the menu button if there are menu views.
            - Enabling the toggle view button if there are toggle views.
            - Updating the tab and shuffle buttons.
            - Calling the super class's mb_configure method if it exists.
        """
        self._has_maximize_button = bool(self.button_maximize or self.DEFAULT_VIEW == self.MINIMIZED)
        if self._has_maximize_button:
            self.enable_ihp("button_minimize")
        if self.menuviews:
            self.enable_ihp("button_menu")
        if len(self.toggleviews):
            self.enable_ihp("button_toggleview")
        self._update_tab_buttons()
        self._update_shuffle_buttons()
        if cb := getattr(super(), "mb_configure", None):
            # permit other overloads.
            await cb()
        self._mb_configured = True

    @traitlets.observe(*_mb_refresh_traitnames)
    def _observe_mb_refresh(self, change: ChangeType):
        if self.closed:
            return
        match change["name"]:
            case "name" | "html_title" | "title_description" | "title_description_tooltip" | "title":
                if self._mb_configured:
                    self.update_title()
                return
            case "border":
                self.layout.border = self.border if self.view else ""
                return
            case "views" | "viewlist":
                self._update_views_onchange()
                return
            case "tabviews":
                self._update_tab_buttons()
                return
            case "menuviews":
                if self.menuviews:
                    self.enable_ihp("button_menu")
                else:
                    self.disable_ihp("button_menu")
            case "button_menu":
                if self.button_menu:
                    self.enable_ihp("box_menu")
                else:
                    self.menu_close()
            case "toggleviews":
                if len(self.toggleviews) > 1:
                    self.enable_ihp("button_toggleview")
                else:
                    self.disable_ihp("button_toggleview")
            case "button_close" if self.button_close:
                self.button_close.tooltip = f"Close {self}"
            case "button_help" if self.button_help:
                self.button_help.tooltip = f"Help for  {utils.fullname(self)}\n"
            case "shuffle_button_views":
                self._update_shuffle_buttons()
            case "shuffle_buttons" if change["old"] is not traitlets.Undefined:
                for b in set(change["old"]).difference(change["new"]):
                    b.close()
        if self._mb_configured:
            self.mb_refresh()

    def _get_help_widget(self):
        """
        Generates and returns a help widget containing documentation for the menubox.

        The documentation is derived from the `help` attribute of the menubox,
        or the menubox's docstring if `help` is not defined. The docstring is
        split into a header and body, and then dedented. The resulting string
        is then converted to markdown.

        Returns:
            ipywidgets.Output: An output widget containing the formatted help text.
        """
        doc = (getattr(self, "help", None) or self.__doc__ or "No help found").split("\n", maxsplit=1)
        help_ = self.fstr(self.HELP_HEADER_TEMPLATE)
        help_ = help_ + doc[0] + ("\n" + textwrap.dedent(doc[1]) if len(doc) == 2 else "")
        with contextlib.suppress(Exception):
            help_ = docstring_to_markdown.convert(help_)
        self.out_help.value = help_
        return self.out_help

    def update_title(self):
        """Updates the title and tooltip of the menubox.

        If the view or title description is not available, the function returns early.
        Otherwise, it enables the 'html_title' widget and formats the title description and tooltip.
        If 'html_title' is available, it sets the description and tooltip, allowing HTML in the description.
        Finally, it updates the label and caption of the title with the cleaned description and tooltip.
        """
        if not self.title_description:
            self.disable_ihp("html_title")
            return
        self.enable_ihp("html_title")
        if self.html_title:
            self.html_title.description_allow_html = True
            self.html_title.description = self.get_html_title_description()
            self.html_title.tooltip = self.get_html_title_description_tooltip()
        if self.trait_has_value("title"):
            self.title.label = self.get_title_label()
            self.title.caption = self.get_title_caption()

    def get_html_title_description(self):
        return self.fstr(self.title_description)

    def get_html_title_description_tooltip(self):
        return cleanhtml(self.fstr(self.title_description_tooltip))

    def get_title_label(self):
        "This is used to update the title"
        return cleanhtml(self.fstr(self.title_description))

    def get_title_caption(self):
        return cleanhtml(self.fstr(self.title_description_tooltip))

    def get_button_loadview(
        self, view, *, description="", disabled=False, button_type: Literal["open", "tab"] = "open"
    ):
        """Creates a button that, when clicked, loads a specified view.
        Args:
            view: The name of the view to load when the button is clicked. Must be a key in `self._current_views`.
            description: The text to display on the button. If not provided, defaults to the view name.
            disabled: Whether the button is initially disabled.
        Returns:
            An ipywidgets.Button instance that, when clicked, loads the specified view.
        Raises:
            ValueError: If `view` is None or an empty string.
            KeyError: If `view` is not a key in `self._current_views`.
        """
        if not view:
            msg = f"A view name is required. {view=}"
            raise ValueError(msg)
        if view not in self._current_views:
            msg = f"{view=} not in {self._current_views}"
            raise KeyError(msg)
        b = ipw.Button(description=str(description or view), disabled=disabled)
        b.add_class(CSScls.button)
        b.add_class(CSScls.button_type_open if button_type == "open" else CSScls.button_type_tab)
        ref = weakref.ref(self)

        def button_clicked(_: ipw.Button):
            if obj := ref():
                obj.load_view(view)

        b.on_click(button_clicked)
        self._view_buttons.add(b)
        return b

    def _update_views_onchange(self):
        self.set_trait("viewlist", tuple(v for v in self.viewlist if v in self.views) or self.views)
        if self.toggleviews:
            self.toggleviews = tuple(v for v in self.toggleviews if v in self._current_views)
        if self.tabviews:
            self.tabviews = tuple(v for v in self.tabviews if v in self._current_views)
        if self.menuviews:
            self.menuviews = tuple(v for v in self.menuviews if v in self._current_views)
        if self.view and (
            (self.task_load_view and self.loading_view not in self._current_views)
            or (self.view not in self._current_views)
        ):
            self.load_view(reload=True)

    def _update_tab_buttons(self):
        buttons = []
        existing = {b.description: b for b in self._tab_buttons}
        for view in self.tabviews:
            if view in existing:
                b = existing[view]
            else:
                b = self.get_button_loadview(view, button_type="tab")
                self._tab_buttons.add(b)
            buttons.append(b)
        self.set_trait("tab_buttons", buttons)

    def _update_shuffle_buttons(self):
        self.set_trait("shuffle_buttons", (self.get_shuffle_button(name) for name in self.shuffle_button_views))

    def _onchange_showbox(self, change: IHPChange):
        if isinstance(change["old"], ipw.Box):
            change["old"].children = (c for c in change["old"].children if c is not self)
        if self.showbox:
            for name in ("button_exit", "button_promote", "button_demote"):
                self.enable_ihp(name)
            if isinstance(self.showbox, ipw.Box) and self not in self.showbox.children:
                self.showbox.children = (*self.showbox.children, self)
            self.show()

    @override
    async def button_clicked(self, b: ipw.Button):
        await super().button_clicked(b)
        match b:
            case self.button_menu:
                self.menu_open()
            case self.button_toggleview if self.toggleviews:
                tvs = self.toggleviews
                i = (tvs.index(self.view) + 1) % len(tvs) if self.view in tvs else 0
                view = self.toggleviews[i]
                self.load_view(view)
            case self.button_promote if self.button_promote:
                if box := self.showbox:
                    box.set_trait("children", utils.move_item(box.children, self, -1))
                    self.button_promote.focus()
            case self.button_demote if self.button_demote:
                if box := self.showbox:
                    box.set_trait("children", utils.move_item(box.children, self, 1))
                    self.button_demote.focus()
            case self.button_menu_minimize:
                self.menu_close()
            case self.button_minimize:
                self.load_view(self.MINIMIZED)
            case self.button_maximize:
                self.maximize()
            case self.button_close:
                self.close(force=True)
            case self.button_exit:
                self.set_trait("showbox", None)
            case self.button_help:
                self.show_help = not self.show_help
                assert self.button_help  # noqa: S101
                self.button_help.description = "❓" if self.show_help else "❔"
                if self.show_help:
                    self.maximize()
            case self.button_activate:
                await self.activate()

    @log.log_exceptions
    def _shuffle_button_on_click(self, b: ipw.Button):
        self.load_shuffle_item(self.shuffle_button_views[b.description], alt_name=b.description)
        self.menu_close()

    def hide_unhide_shuffle_button(self, description: str, hide=True):
        for b in self.shuffle_buttons:
            if b.description == description:
                v = utils.to_visibility(hide, invert=True)
                if v != b.layout.visibility:
                    b.layout.visibility = v
                    if self._mb_configured:
                        self.mb_refresh()
                break

    def get_shuffle_button(self, name: str) -> ipw.Button:
        """Get an existing shuffle button"""
        self.shuffle_button_views[name]  # Test
        b = ipw.Button(description=name)
        b.add_class(CSScls.button)
        b.add_class(CSScls.button_type_shuffle)
        b.on_click(self._shuffle_button_on_click)
        return b

    def obj_in_box_shuffle(self, obj: ipw.Widget) -> ipw.Widget | None:
        if not self.box_shuffle:
            return None
        for c in self.box_shuffle.children:
            if c is obj or isinstance(c, MenuboxWrapper) and c.widget is obj:
                return c
        return None

    def load_shuffle_item(
        self,
        obj_or_name: ipw.Widget | Menubox | str,
        position: Literal["start", "end"] = "start",
        alt_name="",
        ensure_wrapped=False,
    ):
        """Load attribute 'name' into the shuffle box.

        obj_or_name: ipw.Widget | callable | attribute name (nested attribute permitted)

        Note: shuffle box needs to be added somewhere to be visible
        (in a view or sidebar).
        """
        if self.closed:
            return None
        if isinstance(obj_or_name, ipw.Widget):
            obj = obj_or_name
        elif callable(obj_or_name):
            obj = obj_or_name()
        elif isinstance(obj_or_name, str):
            obj = utils.getattr_nested(self, obj_or_name, hastrait_value=False)
        else:
            msg = f"Unable to load {type(obj_or_name)}"
            raise TypeError(msg)
        while callable(obj):
            obj = obj()
        if isinstance(obj, ipw.Widget):
            return self.put_obj_in_box_shuffle(obj, position=position, alt_name=alt_name, ensure_wrapped=ensure_wrapped)
        return None

    if TYPE_CHECKING:

        @overload
        def put_obj_in_box_shuffle(
            self,
            obj: ipw.Widget | mb.Menubox,
            *,
            ensure_wrapped: Literal[True],
            position: Literal["start", "end"] = ...,
            alt_name=...,
        ) -> MenuboxWrapper: ...
        @overload
        def put_obj_in_box_shuffle(  # type: ignore
            self,
            obj: mb.Menubox,
            *,
            ensure_wrapped: Literal[False] = ...,
            position: Literal["start", "end"] = ...,
            alt_name=...,
        ) -> Menubox: ...
        @overload
        def put_obj_in_box_shuffle(
            self,
            obj: ipw.Widget,
            *,
            ensure_wrapped: Literal[False] = ...,
            position: Literal["start", "end"] = ...,
            alt_name=...,
        ) -> MenuboxWrapper: ...

    def put_obj_in_box_shuffle(
        self,
        obj: ipw.Widget | mb.Menubox,
        *,
        ensure_wrapped=False,
        position: Literal["start", "end"] = "end",
        alt_name="",
    ) -> Menubox | MenuboxWrapper:
        """Puts an object into the box shuffle container.

        If the object is already in the box shuffle, it will be moved to the end or beginning
        depending on the `position` argument. If the object is not a Menubox, it will be wrapped
        in a Menubox.

        Note: `box_shuffle` is **NOT** added to a view automatically. Specify it in a view.

        Args:
            obj: The object to put in the box shuffle.
            position: The position to insert the object. Can be "end" or "start".
            alt_name: An alternative name for the object.
            ensure_wrapped: If True, ensures that the object is wrapped in a Menubox.

        Returns:
            The Menubox that contains the object.

        Raises:
            RuntimeError: If the object is a closed Menubox.
            TypeError: If the object is not a widget.
            RuntimeError: If the object is already in the box shuffle but is not a Menubox.
        """
        if (isinstance(obj, mb.Menubox) and obj.closed) or (isinstance(obj, ipw.Widget) and not obj.comm):
            msg = f"The instance of {utils.fullname(obj)} is closed!"
            raise RuntimeError(msg)
        if obj is self:
            msg = f"Adding a menubox to its own shuffle_box is prohibited! {self=}"
            raise RuntimeError(msg)
        if not isinstance(obj, ipw.Widget):
            msg = f"obj of type={type(obj)} is not a widget!"
            raise TypeError(msg)
        obj_ = obj
        if found := self.obj_in_box_shuffle(obj):
            if ensure_wrapped and obj is found and isinstance(obj, Menubox) and obj.showbox is self.box_shuffle:
                obj.set_trait("showbox", None)
            obj_ = found
        self.enable_ihp("box_shuffle")
        assert self.box_shuffle  # noqa: S101
        if not isinstance(obj_, mb.Menubox) or ensure_wrapped and not isinstance(obj_, MenuboxWrapper):
            obj_ = MenuboxWrapper(obj_)
            alt_name = alt_name or "<b>{self.widget.name}<b>" if isinstance(obj, Menubox) else ""
            obj_.title_description = f"<b>{alt_name}<b>" if alt_name else ""
        children = (c for c in self.box_shuffle.children if c not in [obj, obj_])
        self.box_shuffle.children = (*children, obj_) if position == "end" else (obj_, *children)
        obj_.set_trait("showbox", self.box_shuffle)
        if self.button_exit:
            mb.mb_async.call_later(0.1, self.button_exit.focus)
        return obj_

    def deactivate(self):
        "Hide and close existing shell connections."
        self.load_view(None)
        for sc in self.connections:
            sc.close()

    async def activate(self, *, add_to_shell=False, **kwgs: Unpack[ipylab.widgets.AddToShellType]):
        "Maximize and add to the shell."
        await self.wait_init_async()
        if add_to_shell:
            await self.add_to_shell(**kwgs)
        self.maximize()
        if self.task_load_view:
            await asyncio.shield(self.task_load_view)
        return self

    async def add_to_shell(self, **kwgs: Unpack[AddToShellType]) -> ShellConnection:
        return await super().add_to_shell(**kwgs)

    async def show_in_dialog(
        self, title: str = "", *, view: str | None | defaults.NO_DEFAULT_TYPE = defaults.NO_DEFAULT, **kwgs
    ):
        """Display the menubox in a dialog.

        Args:
            title: The title of the dialog.
            view: The view to load. If None, the default view is loaded.
            **kwgs: Keyword arguments passed to self.app.dialog.show_dialog.

        Returns:
            The result of self.app.dialog.show_dialog.
        """
        self.load_view(view)
        title = title or cleanhtml(self.fstr(self.title_description))
        return await self.app.dialog.show_dialog(title, body=self, **kwgs)


class MenuboxWrapper(Menubox):
    DEFAULT_VIEW = "widget"
    widget = tf.InstanceHP(klass=ipw.Widget).configure(allow_none=False, read_only=True, load_default=False)
    views = tf.ViewDict(default=lambda _: {"widget": "widget"})
    css_classes = StrTuple(CSScls.Menubox, CSScls.wrapper)

    def __init__(self, widget: ipw.Widget):
        self.set_trait("widget", widget)
        utils.weak_observe(widget, self.close, names="comm")
        super().__init__()
