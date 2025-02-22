from __future__ import annotations

import contextlib
import enum
from math import nan
from typing import TYPE_CHECKING, Any, Literal, overload

import ipylab
import pandas as pd
import pluggy
from ipywidgets import widgets as ipw

hookimpl = pluggy.HookimplMarker("menubox")  # Used for plugins

if TYPE_CHECKING:

    @overload
    def is_no_value(value: Literal[_NoValue.token, _NoDefault.token]) -> Literal[True]: ...
    @overload
    def is_no_value(value: Any) -> bool: ...
    @overload
    def is_no_value(value: Literal[_NoValue.token, _NoDefault.token], include_na: bool) -> Literal[True]: ...  # noqa: FBT001
    @overload
    def is_no_value(value: Any, include_na: Literal[False]) -> Literal[False]: ...
    @overload
    def is_no_value(value: Any, include_na: Literal[True]) -> bool: ...


def is_no_value(value: Any, include_na=False):
    """Determine if value should be considered as `not a value`."""
    with contextlib.suppress(ValueError):
        if value is NO_VALUE or value is NO_DEFAULT or (include_na and pd.isna(value)):
            return True
    return bool(isinstance(value, str) and value == "<NA>")


class _NoValue(float, enum.Enum):
    """A literal value that represents a null/NaN/None as a place holder

    bool(NO_VALUE) == True
    float(NO_VALUE) == nan
    str(NO_VALUE) == '<NA>'
    """

    token = nan

    def __hash__(self) -> int:
        return id(self)

    def __str__(self) -> str:
        return "<NA>"

    def __repr__(self) -> str:
        return "<NO VALUE>"

    def __bool__(self) -> Literal[True]:
        return True

    def __eq__(self, value: object) -> bool:
        return is_no_value(value, include_na=True)

    def __getattr__(self, name):
        if name == "_value_":
            return nan
        try:
            return getattr(pd.NA, name)
        except AttributeError:
            if name not in ["_typ", "__iter__"]:
                raise
            return None


class _Index(enum.StrEnum):
    token = "--INDEX--"  # noqa: S105

    def __str__(self) -> str:
        return self.token


class _NoDefault(enum.StrEnum):
    token = "--NO_DEFAULT--"  # noqa: S105

    def __str__(self) -> str:
        return self.token


NO_DEFAULT = _NoDefault.token
NO_VALUE = _NoValue.token
INDEX = _Index.token

if TYPE_CHECKING:
    NO_VALUE_TYPE = Literal[NO_VALUE]
    NO_DEFAULT_TYPE = Literal[NO_DEFAULT]

unicode_icons = """
💾→↶-✚↻🗘→←↑↓⇇⇆⇄⇵⇉⇊⇶⇣⇡✂📝🔭✂️📌⎘📋☷‒‾…❔❓👀📜📋📂📁📂📃📄📅📆📡⁞│🔍📖
🔭✎✏✗✘🗙 ✓↩✔ ↩↪	◀► 	▲▽▼ &emsp;➮🐿📉📈🗠🗟📊⚿☯⛔⛖⛗⛴⛵⚙ 🔧⚖️🛠️⚡️🔌📏↤🔨💎
❬❭🔓🔐🔏📪📮📭📬📦📍📎 📐📑📒📓📔📕 📱📷📸📹📺📻🔙🔚🗏🖖🗢🗲🗱🗝🗑🗴🗶💼🎌🌈🌀🌋🌡🏁👥
👽👯🔀🕂🔁🔂💀👿👾👷🐑🗆🗔 🗕🗖◪🗗📥📤🖫🖬🔝ℹ️🚧👋

More here: https://www.unicode.org/charts/PDF/U1F300.pdf
arrows: https://www.unicode.org/charts/PDF/U2190.pdf
box drawing: https://www.w3schools.com/charsets/ref_utf_box.asp
"""  # noqa: RUF001

bmb_kwargs: dict[str, Any] = {  # Modal button
    "layout": {"width": "max-content", "flex": "0 0 auto"},
    "style": {"button_color": "LightGoldenrodYellow"},
}

b_kwargs: dict[str, Any] = {  # Main / primary
    "layout": {"width": "max-content", "flex": "0 0 auto"},
    # "style": {"button_color": "steelblue"},
    "button_style": "primary",
}
bo_kwargs: dict[str, Any] = {  # Open
    "layout": {"width": "max-content", "flex": "0 0 auto"},
    "style": {"button_color": "Ivory"},
}

bw_kwargs: dict[str, Any] = {  # Warning
    "layout": {"width": "max-content", "flex": "0 0 auto"},
    "style": {"button_color": "Orange"},
}
be_kwargs: dict[str, Any] = {  # Error
    "layout": {"width": "max-content", "flex": "0 0 auto"},
    "style": {"button_color": "OrangeRed"},
}
bm_kwargs: dict[str, Any] = {  # Menu
    "layout": {"width": "max-content", "flex": "0 0 auto"},
    "style": {"button_color": "Gainsboro"},
}
bt_kwargs: dict[str, Any] = {  # Toggle
    "layout": {"flex": "0 0 auto", "width": "max-content", "min_width": "30px"},
    "style": {"button_color": "Gainsboro"},
}
bs_kwargs: dict[str, Any] = {  # Shuffle
    "layout": {"flex": "0 0 auto", "width": "max-content", "min_width": "30px"},
    "style": {"button_color": "Bisque"},
}


class NoCloseBox(ipw.Box):
    def close(self, force=False):
        if force:
            super().close()


H_FILL = NoCloseBox(layout={"flex": "1 10 0%", "justify_content": "space-between", "overflow": "hidden"})
V_FILL = NoCloseBox(
    layout={
        "flex_flow": "column",
        "flex": "1 10 auto",
        "justify_content": "space-between",
        "overflow": "hidden",
    }
)


CLS_RESIZE_BOTH = "menubox-resize-both"
CLS_RESIZE_HORIZONTAL = "menubox-resize-horizontal"
CLS_RESIZE_VERTICAL = "menubox-resize-vertical"
CLS_BUTTON_BUSY = "menubox-button-busy"


# Custom stylesheet


css_stylesheet = ipylab.CSSStyleSheet()


class MenuBoxIpylabPlugins:
    @ipylab.hookimpl
    def autostart(self, app: ipylab.App):
        css_stylesheet.replace(f"""
.{CLS_RESIZE_BOTH} {{ resize: both;}}
.{CLS_RESIZE_HORIZONTAL} {{ resize: horizontal;}}
.{CLS_RESIZE_VERTICAL} {{ resize: vertical;}}
.{CLS_BUTTON_BUSY} {{ border: var(--menubox-button-busy-border);}}
        """)
        css_stylesheet.set_variables({"--menubox-button-busy-border": " solid 1px LightGrey"})


ipylab.plugin_manager.register(MenuBoxIpylabPlugins(), name="Menubox")
