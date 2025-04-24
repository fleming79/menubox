from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, Generic, Literal, ParamSpec, TypedDict, TypeVar

import toolz
from traitlets import Bunch, DottedObjectName, HasTraits, TraitType, Unicode

__all__ = ["Bunched", "NameTuple", "StrTuple", "TypedTuple", "ChangeType", "ProposalType", "FromParent"]

if TYPE_CHECKING:
    from menubox.filesystem import HasFilesystem
    from menubox.hashome import HasHome
    from menubox.hasparent import HasParent
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


class Bunched(Bunch):
    """A distinct bunch (hashable)"""

    def __hash__(self):  # type: ignore
        # hash here should be distinct
        # for other hash ideas: https://stackoverflow.com/questions/1151658/python-hashable-dicts#1151705
        return id(self)


class TypedTuple(TraitType[tuple[T, ...], Iterable[T]]):
    name: str  # type: ignore
    info_text = "A trait for a tuple of any length with type-checked elements."

    def __init__(self, trait: TraitType[T, T], default_value=(), **kwargs: Any) -> None:
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
    name: str  # type: ignore
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


class NameTuple(StrTuple):
    """A Trait for a tuple of unique dotted object names."""

    info_text = "A tuple of any length of unique object trait_names (duplicates discarded.)"
    _trait_klass = DottedObjectName

    def _iterate(self, value):
        yield from toolz.unique(value)


class FromParent(TraitType[Callable[[R], T], Callable[[R], T]], Generic[R, T]):
    allow_none = False

    def __init__(self, cast_self: R, default_value: Callable[[R], T], /, *, read_only=True):
        """A trait for a callable that accepts the parent.

        With support for type directly inside the callable.

        Usage:

        ``` python
        class MyClass(HasTraits):
            fp = FromParent(cast(Self, 0), lambda p: p...)

        ```
        """
        super().__init__(default_value=default_value, read_only=read_only)

    def validate(self, obj, value):
        if not callable(value):
            self.error(obj, value, info="Expected a callable")
        return value
