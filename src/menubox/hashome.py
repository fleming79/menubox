from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, ClassVar, Self, override

import traitlets
from ipylab import Icon
from ipylab.common import Fixed, Singular, import_item

from menubox import utils
from menubox.hasparent import HasParent

__all__ = ["HasParent", "Home", "HomeIcon"]

if TYPE_CHECKING:
    from collections.abc import Hashable

    from menubox.repository import Repository



def to_safe_homename(name: str | Home | pathlib.Path):
    n = pathlib.PurePath(utils.sanatise_filename(str(name))).name
    if not n:
        msg = f"Unable convert {name=} to a valid home"
        raise NameError(msg)
    return n


class Home(Singular):
    """A simple object to group objects together using common name.

    Home is singular by name and will return the same object when instantiated with the
    same name. Passing a name as an absolute path will set the repository url to that
    value. The name will take the base folder name, therefore it is not allowed to have
    use folders with the same name but different urls.
    """

    SINGLE_BY: ClassVar = ("name",)
    KEEP_ALIVE = True
    repository = Fixed[Self, "Repository"](
        lambda c: import_item("menubox.repository.Repository")(name="default", url=c["owner"]._url, home=c["owner"])
    )
    name = traitlets.Unicode(read_only=True)

    @override
    @classmethod
    def get_single_key(cls, name: str | Home | pathlib.Path, **kwgs) -> Hashable:
        assert isinstance(name, Home | str | pathlib.Path)  # noqa: S101
        return to_safe_homename(name)

    def __new__(cls, name: str | Home | pathlib.Path, **kwgs):
        if isinstance(name, Home):
            return name
        return super().__new__(cls, name=name, **kwgs)

    def __init__(self, name: str | Home | pathlib.Path,  **kwargs):
        if self.singular_init_started:
            return
        super().__init__(**kwargs)
        self.set_trait("name", to_safe_homename(name))
        path = name if isinstance(name, pathlib.Path) else pathlib.Path(str(name))
        self._url = path.absolute().as_posix() if path.is_absolute() else pathlib.Path().absolute().as_posix()
        self.repository  # noqa: B018 # touch the repository to create it

    def __repr__(self):
        if self.closed:
            return super().__repr__()
        return f"<Home: {self.name}>"

    def __str__(self):
        return self.name

    async def get_repository(self, repository_name: str) -> Repository:
        from menubox.repository import Repository

        repo: Repository = Repository(name=repository_name, home=self)  # type: ignore
        await repo.wait_update_tasks()
        return repo

    def to_dict(self):
        return {'name':self.name, 'repository':self.repository}


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
        if has_home := "home" in cls._traits:
            if home:
                home = Home(home)
            elif isinstance(parent, HasHome):
                home = parent.home
            elif isinstance(parent, Home):
                home = parent
            else:
                msg = "'home' or 'parent' (with a home) must be provided for this class. 'home' may be a string."
                raise NameError(msg)
        inst = super().__new__(cls, home=home, parent=parent, **kwargs)
        if has_home and not inst._HasParent_init_complete:
            inst.set_trait("home", home)
        return inst


class HomeIcon(Icon, HasHome):  # type: ignore
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
