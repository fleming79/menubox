from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from menubox import HasParent
    from menubox.instance import IHPChange, IHPSettings, InstanceHP

hookspec = pluggy.HookspecMarker("menubox")


@hookspec
def instancehp_finalize(inst: InstanceHP, settings: IHPSettings, klass: type):
    """Finalize the settings for the InstanceHP instance."""


@hookspec
def instancehp_default_kwgs(inst: InstanceHP, parent: HasParent, kwgs: dict):
    """Modify the kwgs prior to creating the default."""


@hookspec(firstresult=True)
def instancehp_default_create(inst: InstanceHP, parent: HasParent, args: tuple, kwgs: dict):
    """Create the 'default' instance."""


@hookspec
def instancehp_on_change(inst: InstanceHP, change: IHPChange):
    """Perform actions when the value is changed (including when the default is loaded).

    This is intended for implementing consistent behaviour based on the type of
    the instance, and custom handling of when the default is loaded.
    """
