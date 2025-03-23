from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from menubox import HasParent
    from menubox.instance import IHPHookMappings, InstanceHP

hookspec = pluggy.HookspecMarker("menubox")


@hookspec
def add_css_stylesheet() -> tuple[str, dict]:  # type: ignore
    """Define an additional css stylesheet and/or override css variables."""


@hookspec
def instancehp_finalize(inst: InstanceHP, hookmappings: IHPHookMappings, klass: type):
    """Finalize the settings for the InstanceHP instance."""


@hookspec
def instancehp_default_kwgs(inst: InstanceHP, parent: HasParent, kwgs: dict):
    """Modify the kwgs prior to creating the default."""


@hookspec(firstresult=True)
def instancehp_default_create(inst: InstanceHP, parent: HasParent, args: tuple, kwgs: dict):
    """Create the 'default' instance."""

