from __future__ import annotations

import asyncio
import enum
import math
from typing import TYPE_CHECKING, Any, Literal, cast

import ipylab
import ipywidgets as ipw
import traitlets
from IPython import display as ipd

import menubox.async_run_button
import menubox.widgets
from menubox import mb_async
from menubox.css import CSScls, CSSvar
from menubox.defaults import NO_VALUE
from menubox.instance import IHPChange, IHPCreate, IHPMode, InstanceHP
from menubox.instance import instanceHP_wrapper as ihpwrap
from menubox.trait_types import MP, SS, GetWidgetsInputType, H, ReadOnly, S, T, ViewDictType

__all__ = ["IHPCreate", "InstanceHP", "TF"]

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CoroutineType

    import menubox.menubox
    import menubox.modalbox
    import menubox.persist
    import menubox.repository


class ButtonMode(enum.Enum):
    restart = enum.auto()
    cancel = enum.auto()
    disable = enum.auto()


class TF:
    """A class that provides static methods for creating various types of InstanceHP
    traits, particularly for use with the MenuBox library. It offers shortcuts for
    creating traits based on basic Python types, ipywidgets, and custom MenuBox
    components. These traits are configured using the InstanceHP class (or
    variants like Fixed) to define their behavior within the MenuBox framework.
    The class includes methods for:
    - Basic type traits (Bool, Set, Dict, Str) with default values.
    - A special ViewDict trait for defining views in MenuBox subclasses.
    - A parent trait for establishing hierarchical relationships between
        HasParent subclasses.
    - Traits for ipywidgets and ipylab.
    - Button traits with predefined styles.
    - Traits for MenuBox layout components (MenuboxHeader, MenuboxCenter, etc.).
    - Traits for validated input widgets (TextareaValidate, ComboboxValidate, etc.).
    - Traits for core MenuBox components (Menubox, MenuboxVT).
    - Traits for asynchronous operations (AsyncRunButton).
    - Traits for creating modal dialogs (Modalbox).
    - A trait for selecting repositories (SelectRepository).
    - A trait for asyncio Tasks.
    - A trait for managing persistent objects within MenuBox (MenuboxPersistPool).
    Each method returns an InstanceHP object (or a Fixed object), configured with
    appropriate default values, validation logic, and hooks for seamless
    integration with the MenuBox ecosystem.  The `ihpwrap` function is used to
    simplify the creation of traits for ipywidgets."""

    InstanceHP = InstanceHP
    IHPChange = IHPChange
    IHPCreate = IHPCreate
    IHPMode = IHPMode
    ReadOnly = ReadOnly
    GetWidgetsInputType = GetWidgetsInputType
    ViewDictType = ViewDictType
    ButtonMode = ButtonMode
    CSSvar = CSSvar
    CSScls = CSScls
    MP = MP
    SS = SS
    H = H
    S = S
    T = T
    ipd = ipd
    ipw = ipw
    ipylab = ipylab
    # Basic types

    @staticmethod
    def Str(cast_self: S | int = 0, default_value="") -> InstanceHP[S, str, str]:  # noqa: ARG004
        return InstanceHP(klass=str).configure(
            IHPMode.XL__, default=lambda _: default_value, default_value=default_value
        )

    @staticmethod
    def Bool(cast_self: S | int = 0, /, default_value=False) -> InstanceHP[S, bool, bool]:  # noqa: ARG004
        return InstanceHP(klass=bool).configure(
            IHPMode.XL__, default=lambda _: default_value, default_value=default_value
        )

    @staticmethod
    def Int(cast_self: S | int = 0, /, default_value=0) -> InstanceHP[S, int, int]:  # noqa: ARG004
        return InstanceHP(klass=int).configure(
            IHPMode.XL__, default=lambda _: default_value, default_value=default_value
        )

    @staticmethod
    def Float(cast_self: S | int = 0, /, default_value=math.nan) -> InstanceHP[S, float, float]:  # noqa: ARG004
        return InstanceHP(klass=float).configure(
            IHPMode.XL__, default=lambda _: default_value, default_value=default_value
        )

    @staticmethod
    def Tuple(cast_self: S | int = 0, /, default_value=()) -> InstanceHP[S, tuple, tuple]:  # noqa: ARG004
        return InstanceHP(klass=tuple).configure(IHPMode.XL__, default_value=default_value)

    @staticmethod
    def Set(cast_self: S | int = 0) -> InstanceHP[S, set, set]:  # noqa: ARG004
        return InstanceHP(klass=set).configure(IHPMode.XL__, default_value=set(), default=lambda _: set())

    @staticmethod
    def Dict(cast_self: S | int = 0, *, klass: type[T] = dict) -> InstanceHP[S, T, ReadOnly[T]]:
        return InstanceHP(cast_self, klass=klass).configure(default_value=klass(), default=lambda _: klass())

    # Custom types

    @staticmethod
    def ViewDict(
        cast_self: S | int = 0,  # noqa: ARG004
        value: ViewDictType[S] | None = None,
        /,
    ) -> InstanceHP[S, ViewDictType[S], ViewDictType[S]]:
        """A function to generate an InstanceHP trait.

        Use this in MenuBox subclasses to define `views` and `shuffle_button_views`

        Use `cast(Self, 0)` to provide type hinting inside the lambda functions, if
        this is not desired, just pass `0` instead (or any integer).

        Usage:

        ```
        views = ViewDict(cast(Self, 0), {"view 1": lambda p: p.widget_name})
        ```
        """
        value = value or {}
        return InstanceHP(klass=dict, default=lambda _: value).configure(IHPMode.XL__, default_value={})

    @staticmethod
    def parent(
        cast_self: S | int = 0,  # noqa: ARG004
        /,
        klass: type[SS] | str = "menubox.hasparent.HasParent",
    ) -> InstanceHP[S, SS | None, SS | None]:
        """Define a trait as a parent container for a HasParent subclass.

        Use this to customize the behaviour of the has parent
        """

        def validate_parent(obj: S, value: SS | None):
            if not value:
                return None
            p = value
            while p and p.trait_has_value("parent"):
                if p is obj:
                    msg = f"Unable to set parent of {value!r} because {obj!r} is already a parent or ancestor!"
                    raise traitlets.TraitError(msg)
                p = p.parent  # type: ignore
            return value

        return (
            InstanceHP(klass=klass, default=lambda _: None, validate=validate_parent)
            .configure(IHPMode.X__N)
            .hooks(set_parent=False, on_replace_close=False, remove_on_close=False)
        )  # type: ignore

    # Ipywidgets shortcuts
    Box = staticmethod(ihpwrap(ipw.Box))
    VBox = staticmethod(ihpwrap(ipw.VBox))
    HBox = staticmethod(ihpwrap(ipw.HBox))

    HTML = staticmethod(ihpwrap(ipw.HTML))
    Dropdown = staticmethod(ihpwrap(ipw.Dropdown))
    Combobox = staticmethod(ihpwrap(ipw.Combobox))
    Select = staticmethod(ihpwrap(ipw.Select))
    Text = staticmethod(ihpwrap(ipw.Text))
    Label = staticmethod(ihpwrap(ipw.Label))
    SelectionSlider = staticmethod(ihpwrap(ipw.SelectionSlider, defaults={"options": (NO_VALUE,)}))

    Accordion = staticmethod(ihpwrap(ipw.Accordion))
    IntText = staticmethod(ihpwrap(ipw.IntText))
    RadioButtons = staticmethod(ihpwrap(ipw.RadioButtons))
    Checkbox = staticmethod(ihpwrap(ipw.Checkbox))
    Textarea = staticmethod(ihpwrap(ipw.Textarea))
    GridBox = staticmethod(ihpwrap(ipw.GridBox))
    SelectMultiple = staticmethod(ihpwrap(ipw.SelectMultiple))
    ValueWidget = staticmethod(ihpwrap(ipw.ValueWidget))
    Widget = staticmethod(ihpwrap(ipw.Widget))
    BoundedIntText = staticmethod(ihpwrap(ipw.BoundedIntText))
    FloatText = staticmethod(ihpwrap(ipw.FloatText))
    FloatSlider = staticmethod(ihpwrap(ipw.FloatSlider))
    FloatRangeSlider = staticmethod(ihpwrap(ipw.FloatRangeSlider))
    FloatLogSlider = staticmethod(ihpwrap(ipw.FloatLogSlider))
    FloatProgress = staticmethod(ihpwrap(ipw.FloatProgress))
    IntSlider = staticmethod(ihpwrap(ipw.IntSlider))
    Play = staticmethod(ihpwrap(ipw.Play))
    BoundedFloatText = staticmethod(ihpwrap(ipw.BoundedFloatText))
    SelectionRangeSlider = staticmethod(ihpwrap(ipw.SelectionRangeSlider))
    ColorPicker = staticmethod(ihpwrap(ipw.ColorPicker))

    # Button

    @staticmethod
    def Button(
        cast_self: S | int = 0,
        css_class=CSScls.button_main,
        mode=ButtonMode.restart,
        **kwargs,
    ) -> InstanceHP[S, ipw.Button, ReadOnly[ipw.Button]]:
        "Kwargs are passed to the button init"
        return (
            InstanceHP(cast_self, klass=ipw.Button)
            .configure(default=lambda c: ipw.Button(**kwargs | c["kwgs"]))
            .hooks(
                value_changed=lambda c: c["parent"]._handle_button_change(c, mode),
                add_css_class=(CSScls.button, css_class),
            )
        )

    FileUpload = staticmethod(ihpwrap(ipw.FileUpload, add_css_class=(CSScls.button, CSScls.button_main)))

    MenuboxHeader = staticmethod(
        ihpwrap(
            ipw.HBox,
            on_set=lambda c: c["parent"].dlink(
                source=(c["parent"], "border"),
                target=(c["obj"].layout, "border_bottom"),
            ),
            add_css_class=(CSScls.Menubox_item, CSScls.box_header),
        )
    )
    MenuboxCenter = staticmethod(ihpwrap(ipw.VBox, add_css_class=(CSScls.Menubox_item, CSScls.centerbox)))
    MenuboxMenu = staticmethod(ihpwrap(ipw.HBox, add_css_class=(CSScls.Menubox_item, CSScls.box_menu)))
    MenuboxShuffle = staticmethod(ihpwrap(ipw.HBox, add_css_class=(CSScls.Menubox_item, CSScls.box_shuffle)))

    # Ipywidget String
    HTML_Title = staticmethod(
        ihpwrap(
            ipw.HTML,
            defaults={
                "layout": {
                    "width": "max-content",
                    "padding": "0px 10px 0px 15px",
                    "flex": "0 0 auto",
                },
                "style": {"description_width": "initial"},
                "description_allow_html": True,
            },
        )
    )

    TextareaValidate = staticmethod(ihpwrap(menubox.widgets.TextareaValidate, defaults={"value": ""}))
    ComboboxValidate = staticmethod(ihpwrap(menubox.widgets.ComboboxValidate, defaults={"value": ""}))
    TextValidate = staticmethod(ihpwrap(menubox.widgets.TextValidate, defaults={"value": ""}))
    FloatTextValidate = staticmethod(ihpwrap(menubox.widgets.FloatTextValidate, defaults={"value": 0}))
    IntTextValidate = staticmethod(ihpwrap(menubox.widgets.IntTextValidate, defaults={"value": 0}))
    SelectMultipleValidate = staticmethod(ihpwrap(menubox.widgets.SelectMultipleValidate, defaults={"value": ()}))
    MarkdownOutput = staticmethod(ihpwrap(menubox.widgets.MarkdownOutput))

    # menubox

    Menubox = staticmethod(ihpwrap(cast(type["menubox.menubox.Menubox"], "menubox.menubox.Menubox")))
    MenuboxVT = staticmethod(ihpwrap(cast(type["menubox.menuboxvt.MenuboxVT"], "menubox.menubox.MenuboxVT")))

    # ipylab

    CodeEditor = staticmethod(ihpwrap(ipylab.CodeEditor))
    SimpleOutput = staticmethod(ihpwrap(ipylab.SimpleOutput))
    SplitPanel = staticmethod(ihpwrap(ipylab.SplitPanel))

    @staticmethod
    def AsyncRunButton(
        cast_self: S,
        cfunc: Callable[[S], Callable[..., CoroutineType] | menubox.async_run_button.AsyncRunButton],
        description="Start",
        cancel_description="Cancel",
        kw: Callable[[S], dict] | None = None,
        style: dict | None = None,
        button_style: Literal["primary", "success", "info", "warning", "danger", ""] = "primary",
        cancel_button_style: Literal["primary", "success", "info", "warning", "danger", ""] = "warning",
        tooltip="",
        link_button=False,
        tasktype: mb_async.TaskType = mb_async.TaskType.general,
        **kwargs,
    ):
        return InstanceHP(
            cast_self,
            klass=menubox.async_run_button.AsyncRunButton,
            default=lambda c: menubox.async_run_button.AsyncRunButton(
                parent=c["parent"],
                cfunc=cfunc,
                description=description,
                cancel_description=cancel_description,
                kw=kw,
                style=style,
                button_style=button_style,
                cancel_button_style=cancel_button_style,
                tooltip=tooltip,
                link_button=link_button,
                tasktype=tasktype,
                **kwargs,
            ),
        )

    @staticmethod
    def Modalbox(
        cast_self: S,
        obj: Callable[[S], GetWidgetsInputType[S]],
        title: str,
        expand=False,
        box: Callable[[S], ipw.Box] | None = None,
        title_tooltip="",
        button_expand_description="",
        button_expand_tooltip="Expand",
        button_collapse_description="🗕",
        button_collapse_tooltip="Collapse",
        header_children: Callable[[S], GetWidgetsInputType[S]] = lambda _: "H_FILL",
        on_expand: Callable[[S], Any] = lambda _: None,
        on_collapse: Callable[[S], Any] = lambda _: None,
        orientation="vertical",
        **kwargs,
    ):
        return InstanceHP(
            cast_self,
            klass=cast("type[menubox.modalbox.Modalbox]", "menubox.modalbox.Modalbox"),
            default=lambda c: menubox.Modalbox(
                parent=c["parent"],
                obj=obj,
                title=title,
                expand=expand,
                box=box,
                title_tooltip=title_tooltip,
                button_expand_description=button_expand_description,
                button_expand_tooltip=button_expand_tooltip,
                button_collapse_description=button_collapse_description,
                button_collapse_tooltip=button_collapse_tooltip,
                header_children=header_children,
                on_expand=on_expand,
                on_collapse=on_collapse,
                orientation=orientation,
                **kwargs,
            ),
        )

    @staticmethod
    def SelectRepository(cast_self: H):  # type: ignore
        "Requires parent to have a home"
        return InstanceHP(
            cast_self,
            klass=cast("type[menubox.repository.SelectRepository[H]]", "menubox.repository.SelectRepository"),
        )

    @staticmethod
    def Task():
        return InstanceHP(klass=asyncio.Task).configure(IHPMode.X_RN)

    @staticmethod
    def MenuboxPersistPool(
        cast_self: H,  # noqa: ARG004
        obj_cls: type[MP] | str,
        factory: Callable[[IHPCreate], MP] | None = None,
        **kwgs,
    ) -> ipylab.Fixed[H, menubox.persist.MenuboxPersistPool[H, MP]]:
        """A Fixed Obj shuffle for any Menubox persist object.

        ``` python
        MenuboxPersistPool(cast(Self, 0), obj_cls=MyMenuboxPersistClass)
        ```
        """

        def get_MenuboxPersistPool(c: ipylab.common.FixedCreate[H]):
            from menubox.persist import MenuboxPersistPool as MenuboxPersistPool_

            cls: type[MP] = ipylab.common.import_item(obj_cls) if isinstance(obj_cls, str) else obj_cls  # type: ignore
            return MenuboxPersistPool_(home=c["owner"].home, klass=cls, factory=factory, **kwgs)

        return ipylab.Fixed(get_MenuboxPersistPool)
