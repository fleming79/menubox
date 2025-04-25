from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from menubox import Menubox

hookspec = pluggy.HookspecMarker("menubox")


@hookspec
def add_css_stylesheet() -> tuple[str, dict]:  # type: ignore
    """Define an additional css stylesheet and/or override css variables."""


@hookspec(firstresult=True)
def get_icon(obj: Menubox):
    "Get the icon for the object"
