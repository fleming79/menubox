from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, ClassVar, Self, final, override

import traitlets
from ipylab import Icon
from ipylab.common import Singular

from menubox.hasparent import HasParent

__all__ = ["HasParent", "Home", "HomeIcon"]

if TYPE_CHECKING:
    from collections.abc import Hashable

@final
class Home(Singular):
    SINGLE_BY: ClassVar = ("name",)
    KEEP_ALIVE = True
    name = traitlets.Unicode(read_only=True)

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
        return f"<Home: {self.name}>"

    def __str__(self):
        return self.name

    @traitlets.observe("closed")
    def _home_observe_closed(self, _):
        if self.closed:
            for item in self.instances:
                try:
                    item.close(force=True)
                except TypeError:
                    item.log.exception(f"This object has invalid mro {item=}")
                    item.close()


class _HomeTrait(traitlets.TraitType[Home, Home]):
    """Add this to HasParent classes that should have a home. The trait name must be 'home'."""

    def _validate(self, obj, value: Home | str):
        if not value:
            msg = """`home` is required!
                Hint: `home` can be specified as a string or inherited from a parent."""
            raise RuntimeError(msg)
        home = Home(value)
        if obj.trait_has_value("home") and home is not obj.home:
            msg = "Changing home is not allowed after it is set current={obj.home} new={home}"
            raise RuntimeError(msg)
        home.instances.add(obj)
        return home


class HasHome(HasParent):
    """A Subclass for grouping related objects together by home.

    `home` or `parent` must be specified during instance creation and cannot be changed.
    """

    home = _HomeTrait()

    def __repr__(self):
        if self.closed:
            return super().__repr__()
        cs = "closed: " if self.closed else ""
        home = f"{home}" if self._HasParent_init_complete and (home := getattr(self, "home", None)) else ""
        return f"<{cs}{self.__class__.__name__} name='{self.name}' {home}>"

    def __new__(cls, *, home: Home | str | None = None, parent: HasParent | None = None, **kwargs) -> Self:
        home = cls.to_home(home, parent)
        inst = super().__new__(cls, home=home, parent=parent, **kwargs)
        inst.set_trait("home", home)
        return inst

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


class HomeIcon(HasHome, Icon):
    "An icon singular by home"

    SINGLE_BY = ("home",)
    KEEP_ALIVE = True
    _count = -1

    @classmethod
    def _get_colour(cls):
        colors = [
            "#e6194B",
            "#3cb44b",
            "#ffe119",
            "#4363d8",
            "#f58231",
            "#42d4f4",
            "#f032e6",
            "#fabed4",
            "#469990",
            "#dcbeff",
            "#9A6324",
            "#fffac8",
            "#800000",
            "#aaffc3",
            "#000075",
            "#a9a9a9",
            "#ffffff",
            "#000000",
        ]
        cls._count = cls._count + 1
        return colors[cls._count % len(colors)]

    def __init__(self, home: Home):
        if self.singular_init_started:
            return
        colour = self._get_colour()

        super().__init__(
            home=home,
            name=f"menubox-colourblock-{colour}",
            svgstr=f"""<?xml version="1.0"?>
    <svg xmlns="http://www.w3.org/2000/svg" version="1.2" baseProfile="tiny"
        viewBox="0 0 5 5">
    <desc>Example SVG file</desc>
    <rect x="1" y="1" width="3" height="3" fill="{colour}"/>
    </svg>""",
        )
