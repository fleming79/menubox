from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, ClassVar, Self, final, override

import traitlets
from async_kernel.common import Fixed
from ipylab.common import Singular, import_item

from menubox.hasparent import HasParent
from menubox.trait_types import ReadOnly

__all__ = ["HasParent", "Home"]

if TYPE_CHECKING:
    from collections.abc import Hashable

    from menubox.filesystem import DefaultFilesystem  # noqa: F401


@final
class Home(Singular):
    """A class to group HasHome instances together.

    Closing Home will also force close all HasHome instances.
    """

    SINGLE_BY: ClassVar = ("name",)
    KEEP_ALIVE = True
    name = traitlets.Unicode(read_only=True)
    filesystem = Fixed[Self, "DefaultFilesystem"](
        lambda c: import_item("menubox.filesystem.DefaultFilesystem")(home=c["owner"])
    )

    @override
    @classmethod
    def get_single_key(cls, name: str, **kwgs) -> Hashable:
        assert isinstance(name, str)  # noqa: S101
        return name

    def __new__(cls, name: str | Home, **kwgs):
        if isinstance(name, Home):
            return name
        return super().__new__(cls, name=name, **kwgs)

    def __init__(self, name: str | Home, **kwargs):
        if self.singular_init_started:
            return
        super().__init__(**kwargs)
        self.set_trait("name", name)
        self.instances: weakref.WeakSet[HasHome] = weakref.WeakSet()

    def __repr__(self):
        return f"<Home: {self.name if self.singular_init_started else ''}>"

    def __str__(self):
        return self.name

    @traitlets.observe("closed")
    def _home_observe_closed(self, _):
        if self.closed:
            for item in tuple(self.instances):
                try:
                    item.close(force=True)
                except TypeError:
                    item.log.exception(f"This object has invalid mro {item=}")
                    item.close()


class _HomeTrait(traitlets.TraitType[Home, ReadOnly[Home]]):
    def _validate(self, obj, value: Home | str):
        home = Home(value)
        if obj.trait_has_value("home"):
            msg = "Setting home is prohibited!"
            raise traitlets.TraitError(msg)
        home.instances.add(obj)
        return home


class HasHome(HasParent):
    """A class to group instances by `home`.

    `home` or `parent` must be specified during instance creation and cannot be changed.
    all instances are added to the weakset `home.instances`. All instances are force
    closed when the home instance is closed."""

    home = _HomeTrait()

    def __repr__(self):
        if self.closed or not self._HasParent_init_complete:
            return super().__repr__()
        cs = "closed: " if self.closed else ""
        home = str(self.home)
        name = self.name
        return f"<{cs}{self.__class__.__name__} {home=} {name=}>"

    def __new__(cls, *, home: Home | str | None = None, parent: HasParent | None = None, **kwargs) -> Self:
        home = cls.to_home(home, parent)
        inst = super().__new__(cls, home=home, parent=parent, **kwargs)
        if not inst.trait_has_value("home"):
            inst.set_trait("home", home)
        return inst

    def __init__(self, *, home: Home | str | None = None, parent=None, **kwargs):
        super().__init__(parent=parent, **kwargs)

    @classmethod
    def to_home(cls, home: Home | str | None, parent: HasParent | None):
        if home:
            return Home(home)
        if isinstance(parent, HasHome):
            return parent.home
        if isinstance(parent, Home):
            return parent
        msg = "'home' or 'parent' (with a home) must be provided for this class. 'home' may be a string."
        raise NameError(msg)
