from __future__ import annotations

import enum
import math
from typing import TYPE_CHECKING, Any, Literal, cast

import ipylab
import ipywidgets as ipw
import traitlets
from async_kernel.common import Fixed, import_item
from async_kernel.pending import Pending
from IPython import display as ipd

import menubox.async_run_button
import menubox.widgets
from menubox import mb_async
from menubox.css import CSScls, CSSvar
from menubox.defaults import NO_VALUE
from menubox.instance import IHPChange, IHPCreate, IHPMode, InstanceHP
from menubox.instance import instanceHP_wrapper as ihpwrap
from menubox.trait_types import MP, SS, GetWidgetsInputType, H, ReadOnly, S, T, ViewDictType

__all__ = ["TF", "IHPCreate", "InstanceHP"]

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CoroutineType

    from async_kernel.typing import FixedCreate

    import menubox.menubox
    import menubox.modalbox
    import menubox.persist
    import menubox.repository  # noqa: TC004


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
    - A trait for asyncio async-kernel.Pending.
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
    H_FILL = "H_FILL"
    V_FILL = "V_FILL"

    @staticmethod
    def Str(default_value: str = "", /, *, co_: S | Any = None) -> InstanceHP[S, str, str]:
        return InstanceHP(str, co_=co_).configure(IHPMode.X___, default_value=default_value)

    @staticmethod
    def Bool(default_value: bool, /, *, co_: S | Any = None) -> InstanceHP[S, bool, bool]:
        return InstanceHP(bool, lambda _: default_value, default_value=default_value, co_=co_).configure(IHPMode.X___)

    @staticmethod
    def Int(default_value: int, /, *, co_: S | Any = None) -> InstanceHP[S, int, int]:
        return InstanceHP(
            int,
            lambda _: default_value,
            default_value=default_value,
            validate=lambda _, val: int(val),
            co_=co_,
        ).configure(IHPMode.X___)

    @staticmethod
    def Float(default_value=math.nan, /, *, co_: S | Any = None) -> InstanceHP[S, float, float]:
        return InstanceHP(
            float,
            lambda _: default_value,
            default_value=default_value,
            validate=lambda _, val: float(val),
            co_=co_,
        ).configure(IHPMode.X___)

    @staticmethod
    def Tuple(
        default_value=(),
        /,
        *,
        klass_: type[T] = tuple,  # noqa: ARG004
        co_: S | Any = None,  # pyright: ignore[reportUnusedParameter]
    ) -> InstanceHP[S, T, T]:
        def validate_tuple(owner, value):
            if isinstance(value, tuple):
                return value
            return tuple(value)

        return InstanceHP(  # pyright: ignore[reportReturnType]
            tuple,
            lambda _: default_value,
            default_value=default_value,
            validate=validate_tuple,
            co_=co_,
        ).configure(IHPMode.X___)

    @staticmethod
    def Set(*, klass_: type[T] = set, co_: S | Any = None) -> InstanceHP[S, T, T]:  # noqa: ARG004
        return InstanceHP(set, lambda _: set(), default_value=set(), co_=co_).configure(IHPMode.XL__)  # pyright: ignore[reportReturnType]

    @staticmethod
    def Dict(
        default: Callable[[IHPCreate], dict] | None = None,
        klass_: type[T] = dict,  # noqa: ARG004
        co_: S | Any = None,
    ) -> InstanceHP[S, T, T]:
        "A dict type. Note: klass_ & co_ are only used for type hinting."
        return InstanceHP(dict, default or (lambda _: {}), default_value={}, co_=co_).configure(IHPMode.XL__)  # pyright: ignore[reportReturnType]

    @staticmethod
    def DictReadOnly(
        default: Callable[[IHPCreate], dict] | None = None,
        klass_: type[T] = dict,  # noqa: ARG004
        co_: S | Any = None,
    ) -> InstanceHP[S, T, ReadOnly[T]]:
        "A dict type. Note: klass_ & co_ are only used for type hinting."
        return InstanceHP(dict, default or (lambda _: {}), default_value={}, co_=co_).configure(IHPMode.XLR_)  # pyright: ignore[reportReturnType]

    @staticmethod
    def use_enum(default_value: T, *, co_: S | Any = None) -> InstanceHP[S, T, T]:
        klass = default_value.__class__
        return TF.InstanceHP(
            klass,
            validate=lambda _, val: klass(val),  # pyright: ignore[reportCallIssue]
            default_value=default_value,
            co_=co_,
        ).configure(TF.IHPMode.X___)

    # Custom types

    @staticmethod
    def ViewDict(
        co_: S | Any = None, value: ViewDictType[S] | None = None, /
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
        return InstanceHP(dict, default=lambda _: value.copy(), co_=co_).configure(  # pyright: ignore[reportReturnType, reportAttributeAccessIssue]
            IHPMode.XL__, default_value={}
        )

    @staticmethod
    def parent(
        klass: type[SS] | str = "menubox.hasparent.HasParent",
    ) -> InstanceHP[Any, SS, SS]:
        """Define a trait as a parent container for a HasParent subclass.

        Use this to customize the behaviour of the has parent
        """

        def validate_parent(obj, value: SS | None):
            if not value:
                return None
            p = value
            while p is not None:
                if p is obj:
                    msg = f"Unable to set parent of {value!r} because {obj!r} is already a parent or ancestor!"
                    raise traitlets.TraitError(msg)
                p = p.parent if p.trait_has_value("parent") else None
            return value

        return (  # pyright: ignore[reportReturnType]
            InstanceHP(klass=klass, default=lambda _: None, validate=validate_parent)
            .hooks(set_parent=False, on_replace_close=False, remove_on_close=False)
            .configure(IHPMode.X___)
        )

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
        co_: S | Any = None,
        css_class=CSScls.button_main,
        mode=ButtonMode.restart,
        **kwargs,
    ) -> InstanceHP[S, ipw.Button, ReadOnly[ipw.Button]]:
        "Kwargs are passed to the button init"
        return (
            InstanceHP(ipw.Button, co_=co_)
            .hooks(
                value_changed=lambda c: c["owner"]._handle_button_change(c, mode),
                add_css_class=(CSScls.button, css_class),
            )
            .configure(default=lambda c: ipw.Button(**kwargs | c["kwgs"]))
        )

    FileUpload = staticmethod(ihpwrap(ipw.FileUpload, add_css_class=(CSScls.button, CSScls.button_main)))

    MenuboxHeader = staticmethod(
        ihpwrap(
            ipw.HBox,
            on_set=lambda c: c["owner"].dlink(
                source=(c["owner"], "border"),
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
    DropdownAdd = staticmethod(ihpwrap(menubox.widgets.DropdownAdd, defaults={"value": None}))

    MarkdownOutput = staticmethod(ihpwrap(menubox.widgets.MarkdownOutput))

    # menubox

    Menubox = staticmethod(ihpwrap(cast("type[menubox.menubox.Menubox]", "menubox.menubox.Menubox")))
    MenuboxVT = staticmethod(ihpwrap(cast("type[menubox.menuboxvt.MenuboxVT]", "menubox.menubox.MenuboxVT")))

    # ipylab

    CodeEditor = staticmethod(ihpwrap(ipylab.CodeEditor))
    SimpleOutput = staticmethod(ihpwrap(ipylab.SimpleOutput))
    SplitPanel = staticmethod(ihpwrap(ipylab.SplitPanel))

    @staticmethod
    def AsyncRunButton(
        co_: S,
        /,
        cfunc: Callable[[S], Callable[..., CoroutineType] | menubox.async_run_button.AsyncRunButton],
        description="",
        icon="play",
        cancel_icon="stop",
        kw: Callable[[S], dict] | None = None,
        style: dict | None = None,
        button_style: Literal["primary", "success", "info", "warning", "danger", ""] = "primary",
        cancel_button_style: Literal["primary", "success", "info", "warning", "danger", ""] = "warning",
        tooltip="",
        tasktype: mb_async.TaskType = mb_async.TaskType.general,
        **kwargs,
    ):
        return InstanceHP(
            menubox.async_run_button.AsyncRunButton,
            lambda c: menubox.async_run_button.AsyncRunButton(
                parent=c["owner"],
                name=c["name"],
                cfunc=cfunc,
                description=description,
                icon=icon,
                cancel_icon=cancel_icon,
                kw=kw,
                style=style,
                button_style=button_style,
                cancel_button_style=cancel_button_style,
                tooltip=tooltip,
                tasktype=tasktype,
                **kwargs,
            ),
            co_=co_,
        )

    @staticmethod
    def Modalbox(
        co_: S,
        /,
        obj: Callable[[S], GetWidgetsInputType[S]],
        title: str,
        expand=False,
        box: Callable[[S], ipw.Box] | None = None,
        title_tooltip="",
        icon="",
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
            cast("type[menubox.modalbox.Modalbox]", "menubox.modalbox.Modalbox"),
            lambda c: menubox.Modalbox(
                parent=c["owner"],
                obj=obj,
                title=title,
                expand=expand,
                box=box,
                icon=icon,
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
            co_=co_,
        )

    @staticmethod
    def SelectRepository(co_: H, /):  # pyright: ignore[reportInvalidTypeVarUse]
        "Requires parent to have a home"
        return InstanceHP(
            cast(
                "type[menubox.repository.SelectRepository[H]]",
                "menubox.repository.SelectRepository",
            ),
            co_=co_,
        )

    @staticmethod
    def Pending():
        "An async-kernel Pending"
        return InstanceHP(klass=Pending).configure(IHPMode.X_RN)

    @staticmethod
    def MenuboxPersistPool(
        co_: H,  # noqa: ARG004
        /,
        obj_cls: type[MP] | str,
        factory: Callable[[IHPCreate], MP] | None = None,
        **kwgs,
    ) -> Fixed[H, menubox.persist.MenuboxPersistPool[H, MP]]:
        """A Fixed Obj shuffle for any Menubox persist object.

        ``` python
        MenuboxPersistPool(cast(Self, 0), obj_cls=MyMenuboxPersistClass)
        ```
        """

        def get_MenuboxPersistPool(c: FixedCreate[H]):
            from menubox.persist import MenuboxPersistPool as MenuboxPersistPool_

            cls: type[MP] = import_item(obj_cls) if isinstance(obj_cls, str) else obj_cls  # pyright: ignore[reportAssignmentType]
            return MenuboxPersistPool_(home=c["owner"].home, klass=cls, factory=factory, **kwgs)

        return Fixed(get_MenuboxPersistPool)
