from __future__ import annotations

import asyncio
import contextlib
import inspect
import re
import textwrap
import weakref
from collections.abc import Callable, Iterable
from typing import Any, ClassVar, Final

import docstring_to_markdown
import ipylab
import traitlets
from ipylab import Panel
from ipywidgets import widgets as ipw

import menubox as mb
from menubox import defaults, log, mb_async, utils
from menubox import trait_factory as tf
from menubox.defaults import H_FILL, V_FILL
from menubox.hasparent import HasParent
from menubox.trait_types import ChangeType, ProposalType, StrTuple

# as per recommendation from @freylis, compile once only
CLEANR = re.compile("<.*?>")


def cleanhtml(raw_html):
    "Remove basic html and &emsp;"
    return re.sub(CLEANR, "", raw_html).replace("&emsp;", "")


class Buttons(traitlets.TraitType[tuple[ipw.Button, ...], Iterable[ipw.Button]]):
    default_value = ()

    def validate(self, obj: MenuBox, value):
        return tuple(v for v in value if isinstance(v, ipw.Button) and v._repr_keys)


class MenuBox(HasParent, Panel):
    """An all-purpose widget intended to be subclassed for building gui's."""

    _MINIMIZED: Final = "Minimized"
    _FIRST: Final = "FIRST"
    _view_loading = traitlets.Unicode(allow_none=True)
    _setting_view = False
    _RESERVED_VIEWNAMES: ClassVar[tuple[str | None, ...]] = (_MINIMIZED, _FIRST, None)
    DEFAULT_VIEW: ClassVar[str | None] = _FIRST
    DEFAULT_BORDER = ""
    DEFAULT_LAYOUT: ClassVar[dict[str, str]] = {"max_width": "100%"}
    SHOWBOX_MARGIN: ClassVar[str] = "5px 5px 1px 5px"
    SHOWBOX_APPEND_START = False
    TAB_BUTTON_KW: ClassVar[dict[str, Any]] = dict(defaults.bt_kwargs)
    HELP_HEADER_TEMPLATE = "<h3>ℹ️ {self.__class__.__name__}</h3>\n\n"  # noqa: RUF001
    ENABLE_WIDGETS: ClassVar = ()
    html_discontinued = tf.HTML("Discontinued (closed)")
    html_loading = tf.HTML("Loading ...")
    _MenuBox_init_complete = False

    # Traits
    _mb_configured = False
    show_help = traitlets.Bool()
    _loaded_views = traitlets.Set()
    viewlist = StrTuple()
    toggleviews = StrTuple()
    menuviews = StrTuple()
    tabviews = StrTuple()
    slow_loading_views = StrTuple()
    views = traitlets.Dict(default_value={}, key_trait=traitlets.Unicode())
    view = traitlets.Unicode(allow_none=True, default_value=None)
    view_previous = traitlets.Unicode(allow_none=True, default_value=None)
    title_description = traitlets.Unicode()
    title_description_tooltip = traitlets.Unicode()
    confirm_close_message = traitlets.Unicode()
    remover_button_description_confirm = traitlets.Unicode("Confirm")
    remover_button_description_cancel = traitlets.Unicode("Cancel")
    remover_button_description_middle = traitlets.Unicode("")
    header_left_children = StrTuple("button_exit", "button_minimize", "box_menu", "button_toggleview")
    header_right_children = StrTuple(
        "button_help", "button_activate", "button_promote", "button_demote", "button_close"
    )
    header_children = StrTuple(
        "header_left_children", "html_title", "tab_buttons", "shuffle_buttons", "H_FILL", "header_right_children"
    )
    box_menu_open_children = StrTuple("button_menu_minimize", "get_menu_widgets")
    minimized_children = StrTuple("html_title", "header_right_children")
    shuffle_button_views = traitlets.Dict(
        default_value={},
        value_trait=traitlets.Union([traitlets.Callable(), traitlets.Unicode(), traitlets.Instance(ipw.Widget)]),
        key_trait=traitlets.Unicode(),
    )
    # Trait instances
    _center = traitlets.Any(read_only=True, allow_none=True)
    tab_buttons = Buttons()
    shuffle_buttons = Buttons()

    # Trait factory
    _view_buttons: tf.InstanceHP[weakref.WeakSet[ipw.Button]] = tf.InstanceHP(weakref.WeakSet)
    _tab_buttons: tf.InstanceHP[weakref.WeakSet[ipw.Button]] = tf.InstanceHP(weakref.WeakSet)
    task_load_view = tf.Task()
    html_title = tf.HTML_Title().configure(load_default=False)
    out_help = tf.MarkdownViewer(
        layout={"border": "solid 1px LightGrey", "margin": "5px " * 4, "padding": "5px " * 4}
    ).configure(add_css_class=(defaults.CLS_RESIZE_BOTH,))

    # Buttons
    button_menu = tf.Button_M(description="☰").configure(load_default=False)
    button_toggleview = tf.Button_M(description="➱").configure(load_default=False)
    button_close = tf.Button_E(description="✗", tooltip="Close").configure(load_default=False)
    button_exit = tf.Button_O(description="⇡", tooltip="Leave showbox").configure(load_default=False)
    button_minimize = tf.Button_O(description="🗕", tooltip="Minimize").configure(load_default=False)
    button_maximize = tf.Button_O(description="🗖", tooltip="Restore").configure(load_default=False)
    button_help = tf.Button_O(description="❔").configure(load_default=False)
    button_promote = tf.Button_O(description="⇖", tooltip="Shift up / left").configure(load_default=False)
    button_demote = tf.Button_O(description="⇘", tooltip="Shift down / right").configure(load_default=False)
    button_menu_minimize = tf.Button_M(description="↤", tooltip="Hide menu").configure()
    button_activate = tf.Button_M(description="🐑", tooltip="Add to shell").configure(load_default=False)

    # Boxes
    box_shuffle = tf.BoxShuffle().configure(allow_none=True)
    box_menu = tf.BoxMenu().configure(allow_none=True)
    showbox = traitlets.Any()
    header = tf.BoxHeader().configure(allow_none=True)
    box_center = tf.BoxCenter().configure(allow_none=True)
    _mb_refresh_traitnames = (
        "show_help",
        "html_title",
        "name",
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
        "_center",
        "remover",
        "showbox",
        "tab_buttons",
        "shuffle_buttons",
        "shuffle_button_views",
        "tabviews",
    )

    def __repr__(self):
        cs = "discontinued: " if self.discontinued else ""
        return f"<{cs}{self.__class__.__name__} name:'{self.name if self.trait_has_value('name') else ''}'>"

    def get_log_name(self):
        return f"{utils.limited_string(self, 40)} model_id='{self.model_id}'"

    def __str__(self):
        return self.__repr__()

    @property
    def _current_views(self):
        if not self.viewlist and self.views:
            self.viewlist = tuple(self.views)
        return (*self.viewlist, *self._RESERVED_VIEWNAMES)

    @property
    def view_active(self) -> bool:
        return bool(self.view and self.view != self._MINIMIZED)

    def __init__(
        self,
        *,
        view=defaults.NO_VALUE,
        views: dict[str, str | Callable[[], ipw.Widget | str] | ipw.Widget | Iterable[ipw.Widget | str]] | None = None,
        viewlist: Iterable[str] | None = None,
        tabviews: Iterable[str] | None = None,
        showbox: ipw.Box | None = None,
        **kwargs,
    ):
        if self._MenuBox_init_complete:
            return
        self.observe(self._observe_mb_refresh, names=self._mb_refresh_traitnames)
        try:
            for name in self.ENABLE_WIDGETS:
                self.enable_widget(name)
            if views is not None:
                self.views = views
            if view is defaults.NO_VALUE:
                view = self.DEFAULT_VIEW
            if view:
                kwargs["children"] = (self.html_loading,)
            if self.DEFAULT_LAYOUT and "layout" not in kwargs:
                layout = self.DEFAULT_LAYOUT
                kwargs["layout"] = layout
            if not self.DEFAULT_BORDER and "border" in kwargs.get("layout", {}):
                self.DEFAULT_BORDER = kwargs["layout"]["border"]
            super().__init__(**kwargs)
        except Exception as e:
            self.on_error(e, "__init__ failed")
            super(HasParent, self).__init__()
            raise
        if viewlist is not None:
            self.set_trait("viewlist", viewlist)
        if tabviews is not None:
            self.set_trait("tabviews", tabviews)
        self._MenuBox_init_complete = True
        if showbox:
            self.set_trait("showbox", showbox)
        if view is not None:
            self.load_view(view)

    def discontinue(self, force=False):
        if self.discontinued or (self.KEEP_ALIVE and not force):
            return
        self.set_trait("showbox", None)
        super().discontinue(force)
        self.close()

    def close(self, force=False):
        self.discontinue()
        if self.discontinued:
            super().close(force)

    def enable_widget(self, name: str, overrides: dict | None = None) -> None:
        "Load the widget."
        self.instanceHP_enable_disable(name, True, overrides)

    def disable_widget(self, name: str) -> None:
        "Remove the widget."
        self.instanceHP_enable_disable(name, False)

    @traitlets.validate("views")
    def _vaildate_views(self, proposal: ProposalType):
        views = proposal["value"]
        for view in views:
            if view in self._RESERVED_VIEWNAMES:
                msg = f"{view=} is a reserved name!"
                raise NameError(msg)
        return views

    @traitlets.validate("view")
    def _vaidate_view(self, proposal: ProposalType):
        if self._setting_view:
            if proposal["value"] not in self._current_views:
                msg = f"View{proposal['value']} not in {self._current_views}"
                raise IndexError(msg)
            return proposal["value"]
        self.load_view(proposal["value"])
        return self.view

    @traitlets.validate("viewlist", "toggleviews", "tabviews", "menuviews")
    @log.log_exceptions
    def _validate_viewlist_names(self, proposal: ProposalType):
        views = self.views if proposal["trait"].name == "viewlist" else self._current_views
        val = tuple(v for v in proposal["value"] if v and v in views)
        if proposal["trait"].name == "viewlist" and not val:
            return tuple(views)
        return val

    @traitlets.default("viewlist")
    def _default_viewlist(self):
        return tuple(self.views)

    def maximize(self):
        if self.view_previous and self.view_previous not in self._RESERVED_VIEWNAMES:
            view = self.view_previous
        else:
            view = next(v for v in (self.toggleviews or self.viewlist or self.views))
        self.load_view(view)

    def show(self, *, unhide=False) -> asyncio.Task | None:
        """A non-agressive means to provide an interactive interface."""
        if not self.view and not self._view_loading:
            self.load_view()
        if unhide:
            self.unhide()
        return self.task_load_view

    def hide(self):
        utils.hide(self)

    def unhide(self):
        utils.unhide(self)

    @log.log_exceptions
    def load_view(self, view: str | None = _FIRST, reload=False) -> asyncio.Task[None | str] | None:
        """Load a view by name. By default the first view in  viewlist is loaded.

        The view may be one of the defined views or the always available views.

        Views are registered by overwriting the view dict which is a mapping of the
        view name to the view. The view may be a widget, string rep of the path to
        a method, or a callable. Async and non-async methods are allowed. The only
        requirement is that the returned object must be of widget type.

        ```
        await mb.wait_for(obj.load_view(view))
        ```
        """
        if view == self._FIRST:
            if self._view_loading in self.viewlist:
                view = self._view_loading
            elif self.view in self.viewlist:
                view = self.view
        elif view not in self._current_views:
            msg = f"{view=} not in {self._current_views}"
            raise AttributeError(msg)
        if reload or (view != (self._view_loading or self.view)):
            self._view_loading = view
            self._load_view(view)
            if view in self.slow_loading_views or (
                view not in self._RESERVED_VIEWNAMES and view not in self._loaded_views
            ):
                self.set_trait("children", (self.html_loading,))
        return self.task_load_view

    @mb_async.singular_task(handle="task_load_view", tasktype=mb_async.TaskType.update)
    async def _load_view(self, view: str | None):
        try:
            if not self.viewlist:
                if not self.views:
                    self.views = {"no view": ipw.HTML(f"There is currently no view for {self!r}")}
                self.set_trait("viewlist", self.views)
            if view == self._FIRST or view not in self._current_views:
                view = (self.toggleviews or self.viewlist)[0]  # type: ignore
            self._view_loading = ""
            view = await self.load_view_async(view)
            self._setting_view = True
            self.view = view
        finally:
            self._setting_view = False
        for button in self._view_buttons:
            border = "solid 1px blue" if button.description == view else ""
            mb.utils.set_border(button, border)
        if mb.DEBUG_ENABLED:
            self.log.debug(f"Loaded view: {view}")
        self.menu_close()
        self.mb_refresh()
        view = self.view
        if self.button_menu:
            self.button_menu.tooltip = f"Show menu for {self.__class__.__name__}\nCurrent view: {view}"
        if self.button_toggleview and view in self.toggleviews:
            i = (self.toggleviews.index(view) + 1) % len(self.toggleviews)
            next_view = self.toggleviews[i]
            self.button_toggleview.tooltip = f"Current: {view}\nNext:{next_view}\nAvailable: {self.toggleviews}"
        self._loaded_views.add(view)
        return self.view

    async def load_view_async(self, view: str | None):
        # provisioned to permit intersection by subclasses potentially changing the view
        if not view or self.discontinued:
            self.set_trait("_center", None)
            return None
        if not isinstance(view, str):
            msg = f"view must be a string or None not {type(view)}"
            raise TypeError(msg)

        if view in self._RESERVED_VIEWNAMES:
            match view:
                case self._MINIMIZED:
                    vw = None
                case _:
                    name = f"_view_{view}_get".lower().replace(" ", "_")
                    vw = getattr(self, name)
        else:
            vw = self.views[view]
            if not self._mb_configured:
                await self._configure()
        if isinstance(vw, str):
            vw = utils.getattr_nested(self, vw, None, hastrait_value=False)
            if vw is None:
                msg = f"For {view=} '{self.views[view]}' is not an attribute of {self.__class__}."
                raise ValueError(msg)
            if callable(vw):
                if asyncio.iscoroutinefunction(vw):
                    vw = await vw()
                else:
                    vw = vw()
        self.set_trait("_center", vw)

        if self.view and self.view != self.view_previous:
            self.view_previous = self.view
        return view

    def refresh_view(self):
        """Reload the current view."""
        if not self._MenuBox_init_complete or self.discontinued:
            return
        self.load_view(self._view_loading or self.view, reload=True)

    @mb_async.debounce(0.02)
    async def mb_refresh(self) -> None:
        if self.discontinued or not self._MenuBox_init_complete:
            return
        try:
            if self.task_load_view:
                await self.task_load_view
                return  # Called again by _load_view.
        except TimeoutError:
            self.menuviews = self.viewlist
            self.menu_open()
            self.children = (
                ipw.HTML('<b><font color="red">Load view timeout </font></b>'),
                *tuple(self.get_button_loadview(v) for v in self.viewlist),
            )
        if mb.DEBUG_ENABLED:
            self.enable_widget("button_activate")
        if self.view is None:
            self.children = ()
            return
        self.update_title()
        self._update_header()
        if self.view == self._MINIMIZED:
            self.children = (self.header,)
        else:
            center = tuple(self.get_widgets(self.get_help_widget() if self.show_help else None, self._center))
            if mb.DEBUG_ENABLED and not self.header:
                center = (*center, self.button_activate)
            if self.box_center:
                self.box_center.children = center
                center = self.box_center
            self.children = tuple(self.get_widgets(self.header, center))

    def _update_header(self):
        if self.view == self._MINIMIZED:
            self.enable_widget("header")
            self.enable_widget("button_maximize")
            self.header.children = self.get_widgets(self.button_maximize, self.button_exit, *self.minimized_children)
        else:
            widgets = tuple(self.get_widgets(*self.header_children))
            if set(widgets).difference((H_FILL, V_FILL)):
                self.enable_widget("header")
                self.header.children = widgets
            else:
                self.disable_widget("header")

        if self.header:
            if self.layout.flex_flow and self.layout.flex_flow.startswith("row"):
                self.header.layout.border_bottom = ""
                self.header.layout.margin = "0px 0px 0px 0px"
            else:
                self.header.layout.border_bottom = self.layout.border_top
                self.header.layout.margin = "0px 0px 6px 0px"

    def get_menu_widgets(self):
        return tuple(self.get_button_loadview(v) for v in self.menuviews)

    def menu_open(self):
        self.box_menu.children = tuple(self.get_widgets(*self.box_menu_open_children))

    def menu_close(self):
        if self.box_menu:
            self.box_menu.children = (self.button_menu,) if self.button_menu else ()

    async def _configure(self) -> None:
        """Create widgets and link."""
        if self._mb_configured or self.discontinued:
            return
        if not self._MenuBox_init_complete or not self._HasParent_init_complete:
            raise RuntimeError
        # inspect.getmembers_static maybe an alternative
        # https://docs.python.org/3/library/inspect.html#inspect.getmembers_static
        # Notably traitlets calls dir(obj) during init anyway.
        await self.mb_configure()
        self._mb_configured = True
        self._has_maximize_button = bool(self.button_maximize or self.DEFAULT_VIEW == self._MINIMIZED)
        if self._has_maximize_button:
            self.enable_widget("button_minimize")
        if self.DEFAULT_BORDER and not self.layout.border:
            self.set_border(self.DEFAULT_BORDER)
        if self.menuviews:
            self.enable_widget("button_menu")
        if len(self.toggleviews):
            self.enable_widget("button_toggleview")
        self._update_tab_buttons()
        self._update_shuffle_buttons()

    def _observe_mb_refresh(self, change: ChangeType):
        if self.discontinued:
            return
        match change["name"]:
            case "name" | "html_title" | "title_description" | "title_description_tooltip":
                if self._MenuBox_init_complete:
                    self.update_title()
                return
            case "views" | "viewlist":
                self._update_views_onchange()
                return
            case "tabviews":
                self._update_tab_buttons()
                return
            case "showbox":
                self._onchange_showbox(change)
                return
            case "menuviews":
                if self.menuviews:
                    self.enable_widget("button_menu")
                else:
                    self.disable_widget("button_menu")
            case "button_menu":
                if self.button_menu:
                    self.enable_widget("box_menu")
                else:
                    self.menu_close()
            case "toggleviews":
                if len(self.toggleviews):
                    self.enable_widget("button_toggleview")
                else:
                    self.disable_widget("button_toggleview")
            case "button_close" if self.button_close:
                self.button_close.tooltip = f"Close {self}"
            case "button_help" if self.button_help:
                self.button_help.tooltip = f"Help for  {utils.fullname(self)}\n"
            case "shuffle_button_views":
                self._update_shuffle_buttons()
            case "shuffle_buttons" if change["old"] is not traitlets.Undefined:
                for b in set(change["old"]).difference(change["new"]):
                    b.close()
        if self.view:
            self.mb_refresh()

    def get_help_widget(self):
        """Get an output widget for the help defined for this instance.

        Help can be defined in the main docstring or as the 'help' attribute/property.
        """
        # Custom help permitted with the 'help' attribute/property.
        doc = (getattr(self, "help", None) or self.__doc__ or "No help found").split("\n", maxsplit=1)
        help_ = self.fstr(self.HELP_HEADER_TEMPLATE)
        help_ = help_ + doc[0] + ("\n" + textwrap.dedent(doc[1]) if len(doc) == 2 else "")
        with contextlib.suppress(Exception):
            help_ = docstring_to_markdown.convert(help_)
        self.out_help.value = help_
        return self.out_help

    def update_title(self):
        if not self.view or not self.title_description:
            return
        self.enable_widget("html_title")
        description = self.fstr(self.title_description)
        tooltip = cleanhtml(self.fstr(self.title_description_tooltip))
        if self.html_title:
            self.html_title.description_allow_html = True
            self.html_title.description = description
            self.html_title.tooltip = tooltip
        self.title.label = cleanhtml(description)
        self.title.caption = tooltip

    def get_button_loadview(self, view, *, description="", disabled=False, b_kwargs=defaults.bm_kwargs):
        """"""
        if not view:
            msg = f"A view name is required. {view=}"
            raise ValueError(msg)
        if view not in self._current_views:
            msg = f"{view=} not in {self._current_views}"
            raise KeyError(msg)
        b = ipw.Button(description=str(description or view), disabled=disabled, **b_kwargs)
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
        if self._view_loading and self._view_loading not in self._current_views:
            self.load_view(reload=True)

    def _update_tab_buttons(self):
        buttons = []
        existing = {b.description: b for b in self._tab_buttons}
        for view in self.tabviews:
            if view in existing:
                b = existing[view]
            else:
                b = self.get_button_loadview(view, b_kwargs=self.TAB_BUTTON_KW)
                self._tab_buttons.add(b)
            buttons.append(b)
        self.tab_buttons = buttons

    def _update_shuffle_buttons(self):
        self.shuffle_buttons = (self.get_shuffle_button(name) for name in self.shuffle_button_views)

    def _onchange_showbox(self, change):
        if isinstance(change["old"], ipw.Box):
            utils.trait_tuple_discard(self, owner=change["old"], name="children")
        if self.showbox:
            if not self._MenuBox_init_complete:
                msg = "Cannot set showbox until __init__ is complete!"
                raise RuntimeError(msg)
            if isinstance(self.showbox, ipw.Box):
                if self not in self.showbox.children:
                    if self.SHOWBOX_APPEND_START:
                        self.showbox.children = (self, *self.showbox.children)
                    else:
                        self.showbox.children = (*self.showbox.children, self)
                if self.SHOWBOX_MARGIN:
                    self._previous_margin = self.layout.margin
                    self.layout.margin = self.SHOWBOX_MARGIN
        elif change["old"] is None:
            if hasattr(self, "_previous_margin"):
                self.layout.margin = self._previous_margin

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
            case self.button_promote:
                self.promote()
            case self.button_demote:
                self.demote()
            case self.button_menu_minimize:
                self.menu_close()
            case self.button_minimize:
                self.load_view(self._MINIMIZED)
            case self.button_maximize:
                self.maximize()
            case self.button_close:
                self.discontinue()
            case self.button_exit:
                self.set_trait("showbox", None)
            case self.button_help:
                self.show_help = not self.show_help
                self.enable_widget("button_help")
                self.button_help.description = "❓" if self.show_help else "❔"
            case self.button_activate:
                self.activate()

    def _get_move_obj_info(self):
        if isinstance(self.showbox, ipw.Box):
            obj = self.showbox
            name = "children"
        elif self.parent and self._ptname:
            obj = self.parent
            name = self._ptname
        else:
            msg = "Neither showbox not parent and self._ptname are set."
            raise RuntimeError(msg)
        items = list(getattr(obj, name))
        return obj, name, items, self

    def promote(self):
        """Move up inside parentbox."""
        try:
            obj, name, items, value = self._get_move_obj_info()
        except ValueError:
            return
        idx = items.index(value)
        if idx:
            a = []
            b = []
            for c in items:
                if isinstance(c, ipw.Box) and not c.children:
                    b.append(c)
                    continue
                a.append(c)
            children = a + b
            idx = children.index(value)
            if idx:
                children.insert(idx - 1, children.pop(idx))
            items = children
        obj.set_trait(name, tuple(items))

    def demote(self):
        """Move down inside parentbox."""
        try:
            obj, name, items, value = self._get_move_obj_info()
        except ValueError:
            return
        idx = items.index(value)
        if idx < len(items):
            a = []
            b = []
            for c in items:
                if isinstance(c, ipw.Box) and not c.children:
                    b.append(c)
                    continue
                a.append(c)
            children = a + b
            if idx < len(children):
                children.insert(idx + 1, children.pop(idx))
            items = children
        obj.set_trait(name, tuple(items))

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
                    self.mb_refresh()
                break

    def get_shuffle_button(self, name: str, kw=defaults.bs_kwargs) -> ipw.Button:
        """Get an existing shuffle button"""
        self.shuffle_button_views[name]  # Test
        b = ipw.Button(description=name, **kw)
        b.on_click(self._shuffle_button_on_click)
        return b

    def obj_in_box_shuffle(self, obj: ipw.Widget) -> ipw.Widget | None:
        """Check if obj is in box_shuffle using the function obj_is_in_box.

        Returns either the object, it's wrapper or None.
        """
        return utils.obj_is_in_box(obj, self.box_shuffle)

    @log.log_exceptions
    def load_shuffle_item(self, obj_or_name: ipw.Widget | MenuBox | str, **kwargs):
        """Load attribute 'name' into the shuffle box.

        obj_or_name: ipw.Widget | callable | attribute name (nested attribute permitted)

        Note: shuffle box needs to be added somewhere to be visible
        (in a view or sidebar).
        """
        if self.discontinued:
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
            return utils.show_obj_in_box(obj, box=self.box_shuffle, **kwargs)
        return None

    def set_border(self, border: str | None = None):
        border = self.DEFAULT_BORDER if border is None else border
        self.layout.border = border
        if self.trait_has_value("header") and self.header:
            self.header.layout.border_bottom = border

    async def mb_configure(self):
        """Overload me.

        This function is called when first loading a registered view.

        Use this function to perform actions that are relevant to viewing the
        subclass such as enabling widgets.

        In the subclass include the following:

        ```
        await super().mb_configure()
        ```
        """
        cl = getattr(super(), "mb_configure", None)
        if callable(cl):
            cl = cl()
            if inspect.isawaitable(cl):
                await cl

    def deactivate(self):
        "Remove from shell hide and load view None."
        self.load_view(None)
        self.hide()
        for sc in self.connections:
            sc.close()

    def activate(self, *, add_to_shell=True):
        "Show and to the shell."
        self.show(unhide=True)
        if add_to_shell:
            return self.add_to_shell()
        return None

    def show_in_dialog(self, title: str, **kwgs):
        """Open in a dialog."""
        self.activate(add_to_shell=False)
        return ipylab.app.dialog.show_dialog(title=title, body=self, **kwgs)
