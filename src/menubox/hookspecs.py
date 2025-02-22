from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from menubox.instance import IHPSettings, InstanceHP

hookspec = pluggy.HookspecMarker("menubox")


@hookspec
def instancehp_finalize_settings(inst: InstanceHP, klass: type, settings: IHPSettings):
    """Finalise the settings for the InstanceHP instance."""
