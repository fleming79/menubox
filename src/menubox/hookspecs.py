from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from menubox import HasParent
    from menubox.instance import IHPSettings, InstanceHP

hookspec = pluggy.HookspecMarker("menubox")


@hookspec
def instancehp_finalize_settings(inst: InstanceHP, klass: type, settings: IHPSettings) -> None:
    """Finalise the settings for the InstanceHP instance."""


@hookspec()
def instancehp_default_kwgs(inst: InstanceHP, parent: HasParent, kwgs: dict):
    """Finalise the settings for the InstanceHP instance."""


@hookspec(firstresult=True)
def instancehp_default_create(inst: InstanceHP, parent: HasParent, args: tuple, kwgs: dict):
    """Finalise the settings for the InstanceHP instance."""
