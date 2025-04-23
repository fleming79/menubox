"""A collection of InstanceHP factories.

Factory items include:
* Popular widgets
* Imported widgets to avoid circular imports
* Factories with custom default
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal, cast

import ipylab
import ipywidgets as ipw

import menubox.async_run_button
import menubox.widgets
from menubox import mb_async
from menubox.css import CSScls
from menubox.defaults import NO_VALUE
from menubox.instance import IHPChange, IHPCreate, InstanceHP
from menubox.instance import instanceHP_wrapper as ihpwrap

__all__ = [
    "AsyncRunButton",
    "MenuboxHeader",
    "MenuboxCenter",
    "MenuboxMenu",
    "MenuboxShuffle",
    "Box",
    "Button_main",
    "Button_dangerous",
    "Button_menu",
    "Button_modal",
    "Button_open",
    "Button_shuffle",
    "Button_toggle",
    "Button_cancel",
    "CodeEditor",
    "Combobox",
    "ComboboxValidate",
    "Dropdown",
    "FileUpload",
    "FloatTextValidate",
    "HBox",
    "HTML",
    "HTML_Title",
    "IHPCreate",
    "InstanceHP",
    "IntTextValidate",
    "Label",
    "Select",
    "SelectMultipleValidate",
    "Menubox",
    "Modalbox",
    "MenuboxPersistPool",
    "SelectRepository",
    "Task",
    "Text",
    "TextValidate",
    "TextareaValidate",
    "VBox",
    "MarkdownOutput",
]

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import CoroutineType

    import menubox.filesystem
    import menubox.menubox
    import menubox.modalbox
    import menubox.persist
    import menubox.repository
    import menubox.widgets
    from menubox.hasparent import HasParent
    from menubox.trait_types import MP, H, S


# Basic types


def Bool(
    cast_self: S | int = 0,  # noqa: ARG001
    default: Callable[[IHPCreate[S, bool]], bool | None] = lambda _: False,
) -> InstanceHP[S, bool]:
    return InstanceHP(klass=bool, default=default).configure(
        read_only=False,
        allow_none=False,
        default_value=False,
    )


def Set(
    cast_self: S | int = 0,  # noqa: ARG001
    default: Callable[[IHPCreate[S, set]], set | None] = lambda _: set(),
) -> InstanceHP[S, set]:
    return InstanceHP(klass=set, default=default).configure(
        read_only=False,
        allow_none=False,
        default_value=set(),
    )


def Dict(
    cast_self: S | int = 0,  # noqa: ARG001
    /,
    default: Callable[[IHPCreate[S, dict]], dict | None] = lambda _: {},
) -> InstanceHP[S, dict]:
    return InstanceHP(klass=dict, default=default).configure(
        read_only=False,
        allow_none=False,
        default_value={},
    )


def Str(
    cast_self: S | int = 0,  # noqa: ARG001
    /,
    default: Callable[[IHPCreate[S, str]], str | None] = lambda _: "",
) -> InstanceHP[S, str]:
    return InstanceHP(klass=str, default=default).configure(
        read_only=False,
        allow_none=False,
        default_value="",
    )


# Ipywidgets shortcuts
Box = ihpwrap(ipw.Box)
VBox = ihpwrap(ipw.VBox)
HBox = ihpwrap(ipw.HBox)

HTML = ihpwrap(ipw.HTML)
Dropdown = ihpwrap(ipw.Dropdown)
Combobox = ihpwrap(ipw.Combobox)
Select = ihpwrap(ipw.Select)
Text = ihpwrap(ipw.Text)
Label = ihpwrap(ipw.Label)
SelectionSlider = ihpwrap(ipw.SelectionSlider, defaults={"options": (NO_VALUE,)})


def _bchange(c: IHPChange[HasParent, ipw.Button]):
    c["parent"]._handle_button_change(c)


# Button
Button_main = ihpwrap(ipw.Button, value_changed=_bchange, add_css_class=(CSScls.button, CSScls.button_type_main))
Button_open = ihpwrap(ipw.Button, value_changed=_bchange, add_css_class=(CSScls.button, CSScls.button_type_open))
Button_cancel = ihpwrap(ipw.Button, value_changed=_bchange, add_css_class=(CSScls.button, CSScls.button_type_cancel))
Button_dangerous = ihpwrap(
    ipw.Button, value_changed=_bchange, add_css_class=(CSScls.button, CSScls.button_type_dangerous)
)
Button_modal = ihpwrap(ipw.Button, value_changed=_bchange, add_css_class=(CSScls.button, CSScls.button_type_modal))
Button_menu = ihpwrap(ipw.Button, value_changed=_bchange, add_css_class=(CSScls.button, CSScls.button_type_menu))
Button_toggle = ihpwrap(ipw.Button, value_changed=_bchange, add_css_class=(CSScls.button, CSScls.button_type_toggle))
Button_shuffle = ihpwrap(ipw.Button, value_changed=_bchange, add_css_class=(CSScls.button, CSScls.button_type_shuffle))
FileUpload = ihpwrap(ipw.FileUpload, add_css_class=(CSScls.button, CSScls.button_type_main))

MenuboxHeader = ihpwrap(
    ipw.HBox,
    on_set=lambda c: c["parent"].dlink(
        source=(c["parent"], "border"),
        target=(c["obj"].layout, "border_bottom"),
    ),
    add_css_class=(CSScls.Menubox_item, CSScls.box_header),
)
MenuboxCenter = ihpwrap(ipw.VBox, add_css_class=(CSScls.Menubox_item, CSScls.centerbox))
MenuboxMenu = ihpwrap(ipw.HBox, add_css_class=(CSScls.Menubox_item, CSScls.box_menu))
MenuboxShuffle = ihpwrap(ipw.HBox, add_css_class=(CSScls.Menubox_item, CSScls.box_shuffle))


# Ipywidget String
HTML_Title = ihpwrap(
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


CodeEditor = ihpwrap(ipylab.CodeEditor)

TextareaValidate = ihpwrap(menubox.widgets.TextareaValidate, defaults={"value": ""})
ComboboxValidate = ihpwrap(menubox.widgets.ComboboxValidate, defaults={"value": ""})
TextValidate = ihpwrap(menubox.widgets.TextValidate, defaults={"value": ""})
FloatTextValidate = ihpwrap(menubox.widgets.FloatTextValidate, defaults={"value": 0})
IntTextValidate = ihpwrap(menubox.widgets.IntTextValidate, defaults={"value": 0})
SelectMultipleValidate = ihpwrap(menubox.widgets.SelectMultipleValidate, defaults={"value": ()})
MarkdownOutput = ihpwrap(menubox.widgets.MarkdownOutput)

# menubox

Menubox = ihpwrap(cast(type["menubox.menubox.Menubox"], "menubox.menubox.Menubox"))
MenuboxVT = ihpwrap(cast(type["menubox.menuboxvt.MenuboxVT"], "menubox.menubox.MenuboxVT"))


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


def Modalbox(
    cast_self: S,
    obj: Callable[[S], menubox.utils.GetWidgetsInputType],
    title: str,
    expand=False,
    box: Callable[[S], ipw.Box] | None = None,
    title_tooltip="",
    button_expand_description="",
    button_expand_tooltip="Expand",
    button_collapse_description="🗕",
    button_collapse_tooltip="Collapse",
    header_children: Callable[[S], menubox.utils.GetWidgetsInputType] = lambda _: "H_FILL",
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


def SelectRepository(cast_self: H) -> InstanceHP[H, menubox.repository.SelectRepository[H]]:
    "Requires parent to have a home"
    return InstanceHP(cast_self, klass="menubox.repository.SelectRepository").configure(allow_none=False)


def Task():
    return InstanceHP(klass=asyncio.Task).configure(allow_none=True, load_default=False)


def MenuboxPersistPool(
    cast_self: H,  # noqa: ARG001
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
