from __future__ import annotations

import asyncio
import contextlib
import re
import textwrap
import weakref
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar, Final, Generic, Literal, Self, Unpack, cast, override

import docstring_to_markdown
import ipylab.widgets
import traitlets
from ipylab import Panel, ShellConnection, SimpleOutput
from ipywidgets import widgets as ipw

import menubox as mb
from menubox import defaults, log, mb_async, utils
from menubox.css import CSScls
from menubox.defaults import H_FILL, NO_DEFAULT, V_FILL
from menubox.hasparent import HasParent
from menubox.trait_factory import TF
from menubox.trait_types import RP, ChangeType, GetWidgetsInputType, ProposalType, ReadOnly, StrTuple

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


class Menubox(HasParent, Panel, Generic[RP]):
    """An all-purpose widget intended to be subclassed for building gui's."""

    MINIMIZED: Final = "Minimized"
    RESERVED_VIEWNAMES: ClassVar[tuple[str | None, ...]] = (MINIMIZED,)
    DEFAULT_VIEW: ClassVar[str | None | defaults.NO_DEFAULT_TYPE] = None
    HELP_HEADER_TEMPLATE = "<h3>ℹ️ {self.__class__.__qualname__}</h3>\n\n"  # noqa: RUF001
    _setting_view = False
    _mb_configured = False
    _Menubox_init_complete = False

    parent = TF.parent(cast(type[RP], HasParent)).configure(TF.IHPMode.X__N)

    # Traits
    show_help = TF.Bool(False)
    viewlist = StrTuple()
    toggleviews = StrTuple()
    menuviews = StrTuple()
    tabviews = StrTuple()
    css_classes = StrTuple(CSScls.Menubox, help="Class names to add when the view_active.")

    views = TF.ViewDict(cast(Self, 0)).configure(TF.IHPMode.XL__)
    shuffle_button_views = TF.ViewDict(cast(Self, 0)).configure(TF.IHPMode.XL__)

    border = TF.Str().configure(TF.IHPMode.X__N, default_value=None)
    view = TF.Str().configure(TF.IHPMode.X__N, default_value=None)
    view_previous = TF.Str().configure(TF.IHPMode.X__N, default_value=None)

    title_description = TF.Str()
    title_description_tooltip = TF.Str()

    header_left_children = StrTuple("button_exit", "button_minimize", "box_menu", "button_toggleview")
    header_right_children = StrTuple(
        "button_help", "button_activate", "button_promote", "button_demote", "button_close"
    )
    header_children = StrTuple(
        "header_left_children", "html_title", "tab_buttons", "shuffle_buttons", "H_FILL", "header_right_children"
    )
    box_menu_open_children = StrTuple("button_menu_minimize", "get_menu_widgets")
    minimized_children = StrTuple("html_title", "header_right_children")

    loading_view = TF.InstanceHP(
        str | None, default=lambda _: defaults.NO_DEFAULT, validate=lambda _, value: value
    ).configure(TF.IHPMode.XLRN)

    # Trait instances
    center = traitlets.Any()
    _simple_outputs: TF.InstanceHP[Self, tuple[ipylab.SimpleOutput], ReadOnly] = TF.Tuple().configure(TF.IHPMode.X_R_)
    tab_buttons = Buttons(read_only=True)
    shuffle_buttons = Buttons(read_only=True)
    # Trait factory
    _view_buttons = TF.InstanceHP[Self, weakref.WeakSet[ipw.Button], ReadOnly](klass=weakref.WeakSet)
    _tab_buttons = TF.InstanceHP[Self, weakref.WeakSet[ipw.Button], ReadOnly](klass=weakref.WeakSet)

    task_load_view = TF.Task()
    html_title = TF.HTML_Title().configure(TF.IHPMode.X__N)
    out_help = TF.MarkdownOutput().hooks(add_css_class=(CSScls.resize_both, CSScls.nested_borderbox))

    # Buttons
    button_menu = TF.Button(cast(Self, 0), TF.CSScls.button_menu, icon="bars", tooltip="Open menu").configure(
        TF.IHPMode.X__N
    )
    button_toggleview = TF.Button(cast(Self, 0), TF.CSScls.button_menu, icon="arrow-circle-o-right").configure(
        TF.IHPMode.X__N
    )
    button_help = TF.Button(cast(Self, 0), TF.CSScls.button_open, icon="question-circle", tooltip="help").configure(
        TF.IHPMode.X__N
    )
    button_close = TF.Button(cast(Self, 0), TF.CSScls.button_dangerous, icon="window-close", tooltip="Close").configure(
        TF.IHPMode.X__N
    )
    button_minimize = TF.Button(
        cast(Self, 0), TF.CSScls.button_open, icon="window-minimize", tooltip="Minimize"
    ).configure(TF.IHPMode.X__N)
    button_maximize = TF.Button(
        cast(Self, 0), TF.CSScls.button_open, icon="window-restore", tooltip="Restore"
    ).configure(TF.IHPMode.X__N)
    button_exit = TF.Button(cast(Self, 0), TF.CSScls.button_open, description="⇡", tooltip="Leave showbox").configure(
        TF.IHPMode.X__N
    )
    button_promote = TF.Button(
        cast(Self, 0), TF.CSScls.button_open, description="⇖", tooltip="Shift up / left"
    ).configure(TF.IHPMode.X__N)
    button_demote = TF.Button(
        cast(Self, 0), TF.CSScls.button_open, description="⇘", tooltip="Shift down / right"
    ).configure(TF.IHPMode.X__N)
    button_menu_minimize = TF.Button(
        cast(Self, 0), TF.CSScls.button_menu, description="↤", tooltip="Hide menu"
    ).configure(TF.IHPMode.X__N)
    button_activate = TF.Button(
        cast(Self, 0), TF.CSScls.button_open, icon="window-maximize", tooltip="Add to shell"
    ).configure(TF.IHPMode.X__N)

    # Boxes
    box_shuffle = TF.MenuboxShuffle().configure(TF.IHPMode.XL__)
    box_menu = TF.MenuboxMenu().configure(TF.IHPMode.X__N)
    showbox = (
        TF.InstanceHP(ipw.Box, co_=cast(Self, 0))
        .hooks(on_replace_close=False, remove_on_close=False, value_changed=lambda c: c["owner"]._onchange_showbox(c))
        .configure(TF.IHPMode.X__N)
    )
    header = TF.MenuboxHeader().configure(TF.IHPMode.X_RN)
    _box_minimized = TF.HBox().configure(TF.IHPMode.X__N)
    box_center = TF.MenuboxCenter().configure(TF.IHPMode.XLRN)
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
        """Indicate the view is not None."""
        return self.view is not None

    def __init__(
        self,
        *,
        parent: RP = None,
        view=NO_DEFAULT,
        views: dict[str, GetWidgetsInputType[RP]] | None = None,
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
        else:
            self.refresh_view()
        return self

    @contextlib.contextmanager
    def simple_output(self):
        """A context manager that yields an a SimpleOutput.

        The SimpleOutput has no content and will be closed once the context is exited.

        This function is designed to manage a shared output object that might be
        expensive to initialize or load. It yields a SimpleOutput where the user
        can push any desired output. The output is closed once the view
        is loaded, hence only useful for slow loading views, or could also be used
        as a box for a dialog.

        Yields:
            SimpleOutput.
        """
        out = SimpleOutput()
        out.add_to_tuple(self, "_simple_outputs")
        self.set_trait("children", self._simple_outputs)
        try:
            yield out
        finally:
            out.close()
            self.set_trait("children", self._simple_outputs)

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
        if (b := self.button_toggleview) and view in self.toggleviews:
            i = (self.toggleviews.index(view) + 1) % len(self.toggleviews)
            next_view = self.toggleviews[i]
            b.description = view
            b.tooltip = f"Current: {view}\nNext:{next_view}\nAvailable: {self.toggleviews}"
        return view

    async def get_center(self, view: str | None) -> tuple[str | None, GetWidgetsInputType[RP]]:
        """Override this function to make view loading dynamic.

        **DO NOT CALL DIRECTLY**

        Args:
            view: The name of the view to get the center widget for.

        Returns:
            A tuple containing the name of the view and the center.
        """
        # If you encounter a recursion error, add an await call in a subclss override.
        return view, self.views.get(view, None)  # type: ignore

    @mb_async.throttle(0.05, tasktype=mb_async.TaskType.update)
    async def mb_refresh(self) -> None:
        """Refreshes the menubox content based on its current state.

        This method updates the menubox's children widgets based on several factors:
        - Whether the menubox is initialized and not closed.
        - If a simple output is set, it displays that output and waits for it to close before refreshing again.
        - The current view state (minimized or normal).
        - The presence of a header, center widgets, and help widget.
        - Whether a box layout is used for the center widgets.
        - Applies the border if the view is not minimized.
        """
        if not self._Menubox_init_complete or self.closed:
            return
        if outputs := self._simple_outputs:
            out = outputs[-1]
            ec = asyncio.Event()
            out.observe(lambda _: ec.set(), "closed")
            await ec.wait()
            self.mb_refresh()
            return
        if self.task_load_view:
            await asyncio.sleep(0)
            if task := self.task_load_view:
                with self.simple_output() as out:
                    button_cancel = TF.ipw.Button(description="Cancel")
                    button_cancel.on_click(lambda _: task.cancel("Button click to cancel from mb_refresh"))
                    out.push(f"<b>Loading view {self.view}", button_cancel)
                    await asyncio.wait([task])
                    button_cancel.close()
                    self.mb_refresh()
                    return
        if self.view is None:
            children = ()
        if self.view == self.MINIMIZED:
            for n in ("button_maximize", "button_minimize", "_box_minimized"):
                self.enable_ihp(n)
            self.update_title()
            box = self._box_minimized
            assert box  # noqa: S101
            box.children = self.get_widgets(self.button_exit, self.button_maximize, *self.minimized_children)
            children = (box,)
        else:
            if mb.DEBUG_ENABLED:
                self.enable_ihp("button_activate")
            children = (header,) if (header := self.get_header()) else ()
            center = self.get_widgets(self.center)
            if self.show_help and (help_widget := self._get_help_widget()):
                children = (*children, help_widget)
            if box := self.box_center:
                box.children = center
                children = (*children, box)
            else:
                children = (*children, *center)
        if self._simple_outputs:
            self.mb_refresh()
        else:
            self.set_trait("children", children)
            if self.border is not None:
                self.layout.border = self.border if self.view else ""

    def get_header(self):
        self.update_title()
        widgets = tuple(self.get_widgets(*self.header_children))
        if set(widgets).difference((H_FILL, V_FILL)):
            self.enable_ihp("header")
            if header := self.header:
                header.children = widgets
            return self.header
        return None

    def refresh_view(self, force=False) -> Self:
        """Refreshes the view by reloading if the view isn't already loading."""
        if force or not self.task_load_view:
            self.load_view(reload=True)
        return self

    def get_menu_widgets(self):
        view = self.loading_view if self.loading_view is not NO_DEFAULT else self.view
        buttons = [self.get_button_loadview(v) for v in self.menuviews]
        for b in buttons:
            if b.description == view:
                b.add_class(TF.CSScls.button_active_view)
                b.tooltip = "This is the current view - click to refresh the view."
        return buttons

    def menu_open(self):
        self.enable_ihp("button_menu_minimize")
        if box := self.box_menu:
            box.children = tuple(self.get_widgets(*self.box_menu_open_children))
            box.layout.border = f"var({TF.CSSvar.menubox_border})"

    def menu_close(self):
        if box := self.box_menu:
            box.children = (self.button_menu,) if self.button_menu else ()
            box.layout.border = ""

    async def mb_configure(self) -> None:
        """Configure this widget - called once only when loading the first view.

        This includes:
            - Enabling the maximize button if it exists or if the default view is minimized.
            - Enabling the menu button if there are menu views.
            - Enabling the toggle view button if there are toggle views.
            - Updating the tab and shuffle buttons.
            - Calling the super class's mb_configure method if it exists.
        """
        if self.menuviews:
            self.enable_ihp("button_menu")
        if len(self.toggleviews) > 1:
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
            case "name" | "title_description" | "title_description_tooltip":
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
                (self.enable_ihp if self.menuviews else self.disable_ihp)("button_menu")
            case "button_menu":
                (self.enable_ihp if self.button_menu else self.disable_ihp)("box_menu")
            case "toggleviews":
                (self.enable_ihp if len(self.toggleviews) > 1 else self.disable_ihp)("button_toggleview")
            case "button_close" if b := self.button_close:
                b.tooltip = f"Close {self}"
            case "button_help" if b := self.button_help:
                b.tooltip = f"Help for  {utils.fullname(self)}\n"
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
        b.add_class(CSScls.button_open if button_type == "open" else CSScls.button_tab)
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
            case self.button_help if self.button_help:
                self.show_help = not self.show_help
                self.button_help.icon = "question-circle-o" if self.show_help else "question-circle"
                if self.show_help:
                    self.maximize()
            case self.button_activate:
                await self.activate(add_to_shell=True)

    @log.log_exceptions
    def _shuffle_button_on_click(self, b: ipw.Button):
        widgets = tuple(self.get_widgets(self.shuffle_button_views[b.description]))
        self.load_shuffle_item(widgets, alt_name=b.description)
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
        if name not in self.shuffle_button_views:
            msg = f"{name=} not a shuffle button view options = {list[self.shuffle_button_views]}"
            raise KeyError(msg)
        b = ipw.Button(description=name)
        b.add_class(CSScls.button)
        b.add_class(CSScls.button_shuffle)
        b.on_click(self._shuffle_button_on_click)
        return b

    def obj_in_box_shuffle(self, obj: ipw.Widget | tuple) -> ipw.Widget | None:
        for c in self.box_shuffle.children:
            if c is obj or isinstance(c, MenuboxWrapper) and ((c.widget is obj) or (c.items == obj)):
                return c
        return None

    def load_shuffle_item(
        self,
        obj: GetWidgetsInputType[RP],
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
        obj = tuple(self.get_widgets(obj))
        if len(obj) == 1:
            obj = obj[0]
        return self.put_obj_in_box_shuffle(obj, position=position, alt_name=alt_name, ensure_wrapped=ensure_wrapped)

    def put_obj_in_box_shuffle(
        self,
        obj: ipw.Widget | mb.Menubox | tuple[ipw.Widget, ...],
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
        for obj_ in mb.utils.iterflatten(obj):
            if obj_ is self:
                msg = f"Adding a menubox to its own shuffle_box is prohibited! {self=}"
                raise RuntimeError(msg)
        obj_ = obj
        box = self.box_shuffle
        if found := self.obj_in_box_shuffle(obj):
            if ensure_wrapped and obj is found and isinstance(obj, Menubox) and obj.showbox is box:
                obj.set_trait("showbox", None)
            obj_ = found
        self.enable_ihp("box_shuffle")
        if not isinstance(obj_, mb.Menubox) or ensure_wrapped and not isinstance(obj_, MenuboxWrapper):
            obj_ = MenuboxWrapper(obj_)
            obj_.title_description = f"<b>{alt_name}<b>" if alt_name else ""
        children = (c for c in box.children if c not in [obj, obj_])
        box.children = (*children, obj_) if position == "end" else (obj_, *children)
        obj_.set_trait("showbox", box)
        if self.button_exit:
            mb.mb_async.call_later(0.1, self.button_exit.focus)
        return obj_

    def deactivate(self):
        "Hide and close existing shell connections."
        self.load_view(None)
        for sc in self.connections:
            sc.close()

    async def activate(
        self,
        *,
        add_to_shell=False,
        view: str | None | defaults.NO_DEFAULT_TYPE = NO_DEFAULT,
        **kwgs: Unpack[ipylab.widgets.AddToShellType],
    ):
        "Maximize and add to the shell."
        self.load_view(view)
        task = self.task_load_view
        if add_to_shell:
            await self.add_to_shell(**kwgs)
        if task and not task.done():
            await asyncio.shield(task)
        await self.wait_init_async()
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
    widget = TF.InstanceHP(klass=ipw.Widget).configure(TF.IHPMode.X_RN)
    items = TF.Tuple()
    views = TF.ViewDict(cast(Self, 0), {"widget": lambda p: p.widget or p.items})
    css_classes = StrTuple(CSScls.Menubox, CSScls.wrapper)

    def __init__(self, obj: ipw.Widget):
        if isinstance(obj, tuple):
            self.items = obj
        else:
            self.set_trait("widget", obj)
            utils.weak_observe(obj, self.close, names="comm")
            self.disable_ihp("box_center")
        super().__init__()
