from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, ClassVar, cast

import traitlets

from menubox import trait_types, utils
from menubox.hasparent import HasParent
from menubox.instance import InstanceHP
from menubox.log import log_exceptions

if TYPE_CHECKING:
    from menubox.repository import Repository

__all__ = ["Home"]


def to_safe_homename(name: str):

    n = pathlib.PurePath(utils.sanatise_filename(name)).name
    if not n:
        msg = f"Unable convert {name=} to a valid home"
        raise NameError(msg)
    return n


class Home(HasParent):
    """A simple object to group objects together using common name.

    Home is singular by name and will return the same object when instantiated with the
    same name. Passing a name as an absolute path will set the repository url to that
    value. The name will take the base folder name, therefore it is not allowed to have
    use folders with the same name but different urls.

    Homes with name = 'default' or initiated with private=True are not registered. All
    other homes will appear in _REG.homes.
    """

    SINGLETON_BY: ClassVar = ("name",)
    KEEP_ALIVE = True
    _HREG: _HomeRegister
    _all_homes: ClassVar[dict[str, Home]] = {}
    repository = InstanceHP(cast(type["Repository"], "menubox.repository.Repository"), name="default").configure(
        dynamic_kwgs={"url": "_url"}
    )

    @classmethod
    def validate_name(cls, name: str) -> str:
        return to_safe_homename(name)

    def __new__(cls, name: Home | str | pathlib.Path, **kwargs):
        if isinstance(name, Home):
            return name
        if name not in cls._all_homes:
            name = to_safe_homename(str(name))
            cls._all_homes[name] = super().__new__(cls, name=name, **kwargs)  # type: ignore
        return cls._all_homes[name]

    @log_exceptions
    def __init__(self, name: str | Home | pathlib.Path, *, private=False, **kwargs):
        if self._HasParent_init_complete:
            return
        path = name if isinstance(name, pathlib.Path) else pathlib.Path(str(name))
        self._url = path.absolute().as_posix() if path.is_absolute() else pathlib.Path().absolute().as_posix()
        super().__init__(**kwargs)

        if not private and not self.name.startswith("_"):
            utils.trait_tuple_add(self, owner=self._HREG, name="homes")

    def __repr__(self):
        return f"<Home: {self.name}>"

    def __str__(self):
        return self.name

    async def get_repository(self, repository_name: str) -> Repository:
        repo: Repository = self._CLASS_DEFINITIONS["Repository"](name=repository_name, home=self)  # type: ignore
        await repo.wait_update_tasks()
        return repo


class InstanceHome(traitlets.TraitType[Home, Home]):
    """Use this to ensure the correct home instance is used."""

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


class _HomeRegister(traitlets.HasTraits):
    homes = trait_types.TypedTuple(InstanceHome(), read_only=True)

    @property
    def all_roots(self):
        return tuple(home.repository.root for home in self.homes if not getattr(home, "hidden", False))

    def _load_homes(self, all_roots: tuple[str, ...]):
        self.set_trait("homes", tuple(Home(root) for root in all_roots))


Home._HREG = _HomeRegister()
