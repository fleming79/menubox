from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, Generic, Literal, ParamSpec, TypedDict, TypeVar

import toolz
from ipywidgets import Widget
from traitlets import Bunch, HasTraits, TraitType, Unicode

import menubox

__all__ = ["Bunched", "ChangeType", "NameTuple", "ProposalType", "StrTuple", "TypedTuple"]

if TYPE_CHECKING:
    from menubox.filesystem import HasFilesystem
    from menubox.hashome import HasHome
    from menubox.hasparent import HasParent
    from menubox.instance import InstanceHP
    from menubox.persist import MenuboxPersist
    from menubox.valuetraits import ValueTraits

T = TypeVar("T")
W = TypeVar("W")
R = TypeVar("R", bound=HasTraits)
S = TypeVar("S", bound="HasParent")
SS = TypeVar("SS", bound="HasParent")
RP = TypeVar("RP", bound="HasParent | None")
H = TypeVar("H", bound="HasHome")
HF = TypeVar("HF", bound="HasFilesystem")
V = TypeVar("V", bound="ValueTraits")
MP = TypeVar("MP", bound="MenuboxPersist")


P = ParamSpec("P")


class ReadOnly(Generic[T]):
    "The value is read only"


class ChangeType(TypedDict):
    new: Any
    old: Any
    name: str
    owner: HasTraits
    type: Literal["change"]


class ProposalType(TypedDict):
    trait: TraitType
    value: Any
    owner: HasTraits


type GetWidgetsInputType[T] = (
    None | str | Widget | Callable[[T], GetWidgetsInputType[T]] | Iterable[GetWidgetsInputType[T]]
)


type ViewDictType[T] = Mapping[str, GetWidgetsInputType[T]]


class Bunched(Bunch):
    """A distinct bunch (hashable)"""

    def __hash__(self):  # pyright: ignore[reportIncompatibleVariableOverride]
        # hash here should be distinct
        # for other hash ideas: https://stackoverflow.com/questions/1151658/python-hashable-dicts#1151705
        return id(self)


class TypedTuple(TraitType[tuple[T, ...], Iterable[T]]):
    name: str  # pyright: ignore[reportIncompatibleVariableOverride]
    info_text = "A trait for a tuple of any length with type-checked elements."

    def __init__(
        self,
        trait: TraitType[T, T] | InstanceHP[Any, T, Any],
        default_value=(),
        **kwargs: Any,
    ) -> None:
        if not isinstance(trait, TraitType):
            msg = f"{trait=} is not a TraitType"
            raise TypeError(msg)
        self._trait = trait
        super().__init__(default_value, **kwargs)

    def class_init(self, cls: type[Any], name: str | None) -> None:
        self._trait.class_init(cls, None)
        super().class_init(cls, name)

    def subclass_init(self, cls: type[Any]) -> None:
        if isinstance(self._trait, TraitType):
            self._trait.subclass_init(cls)

    def instance_init(self, obj: Any) -> None:
        self._trait.instance_init(obj)
        return super().instance_init(obj)

    def validate(self, obj, value):
        return tuple(self._trait._validate(obj, v) for v in value)


class StrTuple(TraitType[tuple[str, ...], Iterable[str]]):
    "A Trait for a tuple of strings."

    info_text = "A tuple of any length of str."
    name: str  # pyright: ignore[reportIncompatibleVariableOverride]
    _trait_klass = Unicode
    default_value: tuple[str, ...] = ()

    def __iter__(self):
        yield from self.default_value

    def __init__(self, *default_value, **kwargs):
        """A Tuple of strings of any length."""
        self._trait = self._trait_klass()
        super().__init__(tuple(self._iterate(default_value)), **kwargs)

    def validate(self, obj, value):
        return tuple(self._iterate(self._trait._validate(obj, v) for v in value)) if value else ()

    def _iterate(self, value):
        yield from value


class NameTuple(StrTuple, Generic[R]):
    """
    A Trait to provide typechecker access when specifying defaults.

    Any string is accepted and no validation is perform.

    Use a lambda to specify defaults relative to the instance where it belongs.
    `lambda p: (p.dotted.path.to.trait, )
    """

    info_text = "A tuple of any length of unique items."

    def __init__(self, default: Callable[[R], tuple[Any, ...]] | None = None, /, **kwargs) -> None:
        super().__init__(*menubox.utils.dottedpath(default) if default else (), **kwargs)

    def _iterate(self, value):
        yield from toolz.unique(value)
