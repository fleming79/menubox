from __future__ import annotations

import contextlib
import enum
from math import nan
from typing import TYPE_CHECKING, Any, Literal, overload

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
            if name not in [
                "_typ",
                "__iter__",
                "__pandas_priority__",
                "_pytestfixturefunction",
                "__test__",
                "__bases__",
            ]:
                raise
            return None


class _Enable(enum.Enum):
    token = "Enable"  # noqa: S105

    def __bool__(self) -> Literal[False]:
        return False


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
ENABLE = _Enable.token

if TYPE_CHECKING:
    NO_VALUE_TYPE = Literal[NO_VALUE]
    NO_DEFAULT_TYPE = Literal[NO_DEFAULT]
    ENABLE_TYPE = Literal[ENABLE]


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
