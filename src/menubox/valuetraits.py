from __future__ import annotations

import asyncio
import contextlib
import enum
import inspect
import json
import pathlib
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, TypeVar, overload

import orjson
import ruamel.yaml
import toolz
from traitlets import Dict, HasTraits, Instance, Set, TraitError, TraitType, Undefined, observe

import menubox as mb
from menubox import defaults, utils
from menubox.hasparent import HasParent
from menubox.home import Home, InstanceHome
from menubox.log import log_exceptions
from menubox.pack import json_default_converter, to_yaml
from menubox.trait_types import Bunched, ChangeType, NameTuple, ProposalType

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator

    from fsspec import AbstractFileSystem


__all__ = ["TypedInstanceTuple", "ValueTraits"]

T = TypeVar("T")


class _ValueTraitsValueTrait(TraitType[Callable[[], dict[str, Any]], str | dict[str, Any]]):
    """Trait ValueTraits.value Will notify every time a value is validated."""

    info_text = "ValueTraits value"
    default_value = defaults.NO_VALUE

    def set(self, obj: ValueTraits, value):  # type: ignore
        try:
            if obj.vt_validating:
                return
        except AttributeError:
            # Ignore pre-init changes
            return
        new_value = self._validate(obj, value)
        if not self.name:
            msg = "Name must be set"
            raise RuntimeError(msg)
        obj._trait_values[self.name] = new_value
        obj._notify_trait(self.name, obj._value, new_value)

    def _validate(self, obj: ValueTraits, value):
        if obj.vt_validating:
            msg = "Validation in progress!"
            raise RuntimeError(msg)
        obj.vt_validating = True
        try:
            obj._load_value(value)
            return obj._value
        finally:
            obj.vt_validating = False


class TypedInstanceTuple(TraitType[tuple[T, ...], Iterable[T]]):
    name: str
    default_value = ()
    info_text = "A tuple that can spawn new instances"
    validating = False
    _callback_specs: ClassVar[dict[str, tuple[str, ...]]] = {
        "_on_add": ("obj",),
        "_on_remove": ("obj",),
        "_factory": ("kwargs",),
    }

    _update_by = "name"
    _update_item_names: tuple[str, ...] = ()
    _spawn_new_instances: bool = True
    _set_parent = True
    _discontinue_on_remove = True
    _factory = ""
    _on_add = ""
    _on_remove = ""

    @contextlib.contextmanager
    def _busy_validating(self):
        self.validating = True
        try:
            yield
        finally:
            self.validating = False

    def __set_name__(self, owner: ValueTraits, name: str):
        # Register this tuplename with owner (class)
        self.name = name  # type: ignore
        d = dict(owner._vt_tit_names)
        if not owner._vt_tit_names:
            d = {}
            # Check for inheritance from other classes
            for cls in owner.__class__.mro(owner.__class__):  # type: ignore
                if issubclass(cls, ValueTraits) and cls._vt_tit_names:
                    d.update(cls._vt_tit_names)
        owner._vt_tit_names = d | {  # type: ignore
            name: {
                "update_by": self._update_by,
                "update_item_names": self._update_item_names,
                "new_update_inst": self.new_update_inst,
                "trait": self._trait,
                "SINGLETON_BY": self._get_SINGLETON_BY,
            }
        }

    def _get_SINGLETON_BY(self):
        names = []
        for trait in self._all_traits(self):
            if (
                isinstance(trait, Instance)
                and issubclass(trait.klass, HasParent)  # type: ignore
                and trait.klass.SINGLETON_BY
            ):
                names.extend(trait.klass.SINGLETON_BY)
        return tuple(toolz.unique(names))

    @staticmethod
    def _all_traits(obj):
        if hasattr(obj, "_trait"):
            if hasattr(obj._trait, "trait_types"):
                for obj_ in obj._trait.trait_types:
                    yield from TypedInstanceTuple._all_traits(obj_)
            else:
                yield obj._trait
        if isinstance(obj, TraitType):
            yield obj

    def __init__(self, trait: TraitType[T, T], *, allow_none=False, read_only=False, help=""):  # noqa: A002
        """A tuple for ValueTraits where elements can be spawned and observed."""
        if not isinstance(trait, TraitType):
            msg = f"{trait=} is not a TraitType"
            raise TypeError(msg)
        self._trait = trait
        super().__init__(allow_none=allow_none, read_only=read_only, help=help)

    def class_init(self, cls: type[Any], name: str | None) -> None:
        super().class_init(cls, name)
        self._trait.class_init(cls, None)

    def subclass_init(self, cls: type[ValueTraits]):  # type: ignore
        if not issubclass(cls, ValueTraits):
            msg = "TypedInstanceTuple is only compatible with ValueTraits or a subclass."
            raise TypeError(msg)
        super().subclass_init(cls)
        # Required to ensure instance_init is always called during init
        if hasattr(cls, "_instance_inits") and self.instance_init not in cls._instance_inits:
            cls._instance_inits.append(self.instance_init)

    def instance_init(self, obj: ValueTraits):
        """Init an instance of TypedInstanceTuple."""
        self._trait.instance_init(obj)
        super().instance_init(obj)
        utils.weak_observe(
            obj,
            obj._vt_tuple_on_change,
            names=self.name,
            tuplename=self.name,
            on_add=self._get_func(obj, "_on_add"),
            on_remove=self._get_func(obj, "_on_remove"),
            _tuple_on_add=self._tuple_on_add,
            _tuple_on_remove=self._tuple_on_remove,
            pass_change=True,
        )  # type: ignore

    def validate(self, obj: ValueTraits, value: ProposalType):
        if obj.discontinued:
            return ()
        try:
            if self.validating:
                return getattr(obj, self.name) if obj.trait_has_value(self.name) else self.default()
            with self._busy_validating():
                values = []
                for i, v in enumerate(value):
                    val = v
                    try:
                        self._trait._validate(obj, val)
                    except Exception as e:
                        if not isinstance(val, dict):
                            msg = f"Invalid element detected of type {type(val)}"
                            raise TypeError(msg) from e
                        val = self.new_update_inst(obj, val, i)
                    if val is None:
                        continue
                    if id(val) not in map(id, values):
                        values.append(val)
                return tuple(values)
        except Exception as e:
            obj.on_error(e, "Trait validation error", self)
            raise

    def new_update_inst(self, obj, kw: dict, index=None):
        if inst := self._find_update_item(obj, kw, index=index):
            return inst
        if not self._spawn_new_instances:
            msg = f"Spawn new instance is prohibited for {utils.fullname(obj)}.{self.name}"
            raise RuntimeError(msg)
        factory = self._get_func(obj, "_factory")
        if not callable(factory):
            factory = getattr(self._trait, "klass", None)
        if not factory:
            msg = f"A factory is required for {utils.fullname(obj)}.{self.name}"
            raise RuntimeError(msg)
        try:
            if self._set_parent:
                kw = {"parent": obj} | kw
            return factory(**kw)
        except Exception as e:
            if mb.DEBUG_ENABLED:
                raise
            msg = (
                f"Unable to create new instance of {self._trait}"
                f" factory={utils.fullname(obj)}.{self._factory}\n"
                f"kw={utils.limited_string(kw, 60)}"
            )
            raise ValueError(msg) from e

    def _find_update_item(self, obj, kw: dict, index: int | None):
        """Check if an item exists in current tuple matching update_by in kw.

        The first inst found is updated with kw and returned.
        """
        ub = self._update_by
        if ub is None:
            return None
        if ub is defaults.INDEX:
            if index is None:
                return None
        elif ub not in kw:
            return None
        current = getattr(obj, self.name)
        for i, inst in enumerate(current):
            if index is not None and ub is defaults.INDEX:
                if i < index:
                    continue
            else:
                ub_ = utils.getattr_nested(inst, ub, hastrait_value=True)
                if ub_ != kw[ub]:
                    continue
            default_setter = getattr(inst, "setter", obj.setter)
            if isinstance(inst, ValueTraits):
                inst.value = kw
            else:
                for k, v in kw.items():
                    if k == ub:
                        continue
                    utils.setattr_nested(inst, k, v, default_setter=default_setter)
            return inst
        return None

    def _get_func(self, obj: ValueTraits, attr: str) -> Callable | None:
        """Get a function defined in the mapping by from metadata.

        These can be set by .tag()
        """
        if mb.DEBUG_ENABLED and attr not in self._callback_specs:
            msg = f"{attr} has not been mapped to a function for {obj.__class__}"
            raise KeyError(msg)
        funcname = getattr(self, attr)
        if not funcname:
            return None
        func = getattr(obj, funcname, None)
        if func is None:
            msg = f'The callback "{utils.fullname(obj)}.{funcname}" is not defined!'
            raise AttributeError(msg)
        if not callable(func):
            msg = f"{utils.fullname(obj)}.{funcname} is not callable!"
            raise TypeError(msg)
        sig = inspect.signature(func)
        if set(self._callback_specs[attr]).difference(sig.parameters):
            msg = f"{func} is missing the following named arguments: {list(self._callback_specs[attr])})"
            raise AttributeError(msg)
        return func

    def configure(
        self,
        *,
        update_by="name",
        update_item_names: tuple[str, ...] | str = (),
        spawn_new_instances: bool = True,
        set_parent=True,
        discontinue_on_remove=True,
        factory="",
        on_add="",
        on_remove="",
    ) -> Self:
        """Change the behaviour of the typed instance tuple.

        Parameters
        ----------
        update_by: str
            If an existing instance with attribute name corresponding to a passed dict,
            it will be updated rather than spawning a new instance.
        update_item_names:
            The names of traits of each instance to observe for a change. Changes are
            passed to `on_change` of the ValueTraits object.
        spawn_new_instances: bool
            If set False, it will not attempt to create a new instance when a
             dict is passed. Thus factory will not be used, updating values
             is still permitted.
        set_parent: bool
            Set the parent of the trait items to the value_traits instance to which this
            tuple belongs.
            *note:* parent is passed as a kwarg during instantiation of new objects.
        discontinue_on_remove: bool
            Discontinue the instance once it is removed

        factory (**kwargs): str
            The name of a method of the object to which the tuple belongs.
            It must return an instance of the specified trait.

        on_add(obj) : str
            The name of a method called when a new object is added to the tuple.
            Each new object is passed.

        on_remove(obj): st | None
            on_add and on_remove are called on each element that is added / removed
            existing items not called)
            signature : on_add(obj)


        expected convention:
            * method (self, change or obj)
            * class method

        """
        self._update_by = update_by if update_by is defaults.INDEX else str(update_by)
        self._update_item_names = tuple(utils.iterflatten(update_item_names))
        self._spawn_new_instances = bool(spawn_new_instances)
        if self._spawn_new_instances and not factory and not getattr(self._trait, "klass", None):
            msg = "A factory is required when trait doesn't specify a klass (such as Union)"
            raise RuntimeError(msg)
        self._set_parent = bool(set_parent)
        self._discontinue_on_remove = bool(discontinue_on_remove)
        if not self._set_parent:
            self._tuple_on_add = None  # type: ignore
        if not self._discontinue_on_remove:
            self._tuple_on_remove = None  # type: ignore
        self._on_add = on_add
        self._on_remove = on_remove
        self._factory = factory
        return self

    def _tuple_on_add(self, parent: ValueTraits, obj: HasParent):
        if isinstance(obj, HasParent) and self._set_parent:
            obj.parent = parent
            obj.set_trait("_ptname", self.name)

    def _tuple_on_remove(self, _: ValueTraits, obj: HasParent):
        if self._discontinue_on_remove:
            utils.close_ipw(obj, discontinue_hasparent=True)

    def tag(self, **kw):
        raise NotImplementedError


class _TypedTupleRegister(HasParent):
    """A simple register to track observer,name pairs."""

    if TYPE_CHECKING:
        parent: ValueTraits
    reg: set[tuple[HasTraits, str]] = Set()  # type: ignore

    @observe("reg")
    def _observe_reg(self, change: ChangeType):
        self.parent._vt_observe_vt_reg_value(change)

    def change_handler(self, change: ChangeType):
        """"""
        if self.parent:
            self.parent._vt_on_reg_tuples_change(change, self.name)
        else:
            pass


class CallbackMode(enum.Enum):
    external = enum.auto()
    internal = enum.auto()


INTERNAL = CallbackMode.internal
EXTERNAL = CallbackMode.external


class ValueTraits(HasParent):
    """Provides for monitoring and setting of nested traits.

    The value is the method `to_dict`, which 'changes' when items registered
    in the tuple (attributes) `value_traits`, `value_traits_persist` and
    TypedInstanceTuples. The value change notification is emitted once after internal
    notificates propagate, preventing 'noisy' changes to be emitted.

    The `to_jason` method provides for round tripping of values and can
    restored by setting the attribute `value` (supported during init).

    The persist traits are updated whenever the value changes so the value
    trait can be observed.

    value: A dictionary containing key values for the current value_traits or
        value_traits_persist. The value may also be a callable that returns a
        dict or a yaml/json dict.

    value_traits:  a NameTuple of traits to monitor
    value_traits_persist: a NameTuple of traits to persist.
    """

    _STASH_DEFAULTS = False
    _AUTO_VALUE = True  # Also connects the trait 'value' on the trait if it is found.
    _ignore_change_cnt = 0
    _vt_reg_value_traits_persist: set[tuple[HasTraits, str]] = Set()  # type: ignore
    _vt_reg_value_traits: set[tuple[HasTraits, str]] = Set()  # type: ignore
    _vt_tuple_reg: Dict[str, _TypedTupleRegister] = Dict(read_only=True)
    _vt_tit_names: ClassVar[dict] = {}
    _vt_busy_updating_count = 0
    _vt_init_complete = False
    dtype = "dict"
    home = InstanceHome()
    value = _ValueTraitsValueTrait()
    parent_dlink = NameTuple()
    value_traits = NameTuple()
    value_traits_persist = NameTuple()
    _prohibited_parent_links: ClassVar[set[str]] = {"home"}
    _prohibited_value_traits: ClassVar[set[str]] = {"parent"}
    if TYPE_CHECKING:
        _value: Callable

    @contextlib.contextmanager
    def ignore_change(self):
        """Ignore all changes whilst in this context.

        Applies to any changes obsevered using the change registers associated with
        value_traits, value_traits_persist, and any TypedInstanceTuple traits.

        Changes observed by other means such as direct observation, link or dlink
        are not affected.
        """
        self._ignore_change_cnt = self._ignore_change_cnt + 1
        try:
            yield
        finally:
            self._ignore_change_cnt = self._ignore_change_cnt - 1

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        cs = "discontinued: " if self.discontinued else ""
        home = f"home:{self.home}" if self._vt_init_complete else ""
        return f"<{cs}{self.__class__.__name__} name='{self.name}' {home}>"

    def __init_subclass__(cls, **kwargs) -> None:
        tn_ = dict(cls._vt_tit_names)
        for c in cls.mro():
            if c is __class__:
                break
            if issubclass(c, ValueTraits) and c._vt_tit_names:
                # Need to copy across other unregistered TypedInstanceTuple mappings
                for name in c._vt_tit_names:
                    if name not in tn_:
                        tn_[name] = c._vt_tit_names[name]
            if c is HasTraits:
                msg = (
                    "This class has invalid MRO please ensure ValueTraits is higher "
                    "up the MRO. This can be done by changing the inheritance order"
                    "in the class definition."
                )
                raise RuntimeError(msg)
        cls._vt_tit_names = tn_
        super().__init_subclass__(**kwargs)

    def _init_CHECK_PARENT(self):
        if self.parent:
            msg = "Parent must not be set prior to init of ValueTraits."
            raise RuntimeError(msg)

    def __new__(cls, *, home: Home | str | None = None, parent: HasParent | None = None, **kwargs):
        if home:
            home = Home(home)
        elif isinstance(parent, ValueTraits):
            home = parent.home
        elif isinstance(parent, Home):
            home = parent
        else:
            home_ = getattr(cls.home, "default_value", "")
            if home_:
                home = Home(home_)
            else:
                msg = "'home' or 'parent' (with a home) must be provided. 'home' may be a string."
                raise NameError(msg)
        inst = super().__new__(cls, home=home, parent=parent, **kwargs)
        if not inst._vt_init_complete and home and inst.has_trait("home"):  # type: ignore
            inst.set_trait("home", home)
        return inst

    def __init__(
        self,
        *,
        home: Home | str | None = None,
        parent: HasParent | None = None,
        _ptname="",  # TypedInstanceTuple name of parent
        value_traits: Collection[str] | None = None,
        value_traits_persist: Collection[str] | None = None,
        value: dict | Callable[[], dict] | None | str = None,
        **kwargs,
    ):
        if value is None:
            value = {}
        if self._vt_init_complete:
            return
        if hasattr(self, "vt_validating"):
            msg = (
                f"{utils.fullname(__class__)}__ini__ BUG. If there are items\n"
                f" in {self.SINGLETON_BY=} check for bugs in the init of the object.\n"
                "Otherwise check which validation is occurring before init is complete."
            )
            raise RuntimeError(msg)
        self._init_CHECK_PARENT()
        self.vt_validating = False
        self.vt_updating = False
        self.set_trait("value_traits", value_traits or self.value_traits)
        self.set_trait("value_traits_persist", value_traits_persist or self.value_traits_persist)
        vts = []
        for v in (*self.value_traits_persist, *self.value_traits, *self._vt_tit_names):
            if v not in vts:
                vts.append(v)
        if callable(value):
            value = value()
        if isinstance(value, str):
            value = ruamel.yaml.YAML(typ="safe").load(value)
        if not isinstance(value, dict):
            msg = "Expected a dict"
            raise TypeError(msg)
        value = dict(value)
        # Extract kwargs that overlap with value_traits/persist in order or vts
        for n in vts:
            name = n
            if name in kwargs:
                value[name] = kwargs.pop(name)
            elif not name.endswith(".value"):
                # Also handle .value in case it is set explicitly
                name = name + ".value"
                if name in kwargs:
                    value[name] = kwargs.pop(name)
        for k in list(kwargs):
            if "." in k:
                value[k] = kwargs.pop(k)
        self._init_CHECK_PARENT()
        self._init_tuple_reg()
        self._vt_update_reg_value_traits()
        self._vt_update_reg_value_traits_persist()
        self.observe(
            self._vt_value_traits_observe,
            names=("value_traits", "value_traits_persist"),
        )
        self._vt_init_complete = True
        super().__init__(parent=parent, _ptname=_ptname, **kwargs)
        # Parent must be set prior to setting value because HasParent
        # may load data from a parent which is need to load values
        if self._STASH_DEFAULTS:
            self._DEFAULTS = self.to_dict()
        if value:
            self.set_trait("value", value)

    async def init_async(self):  # type: ignore
        corofunc = super().init_async
        if corofunc:
            if not asyncio.iscoroutinefunction(corofunc):
                msg = f"{corofunc=} is not a coroutine function! {type(corofunc)}"
                raise TypeError(msg)
            await corofunc()

    @observe("discontinued")
    def _vt_observe_discontinued(self, change: ChangeType):
        # Unobserve by clearing the registers
        self._ignore_change_cnt = self._ignore_change_cnt + 1
        self._vt_tuple_reg.clear()
        self._vt_reg_value_traits = set()
        self._vt_reg_value_traits_persist = set()

    def _init_tuple_reg(self):
        """Create registers TypedInstanceTuples."""

        for name in self._vt_tit_names:
            self._vt_tuple_reg[name] = _TypedTupleRegister(name=name, parent=self)
            self._vt_update_reg_tuples(name)

    def tag(self, **kw):
        msg = f"The metadata passed be use {list(kw)}"
        raise NotImplementedError(msg)

    @observe("_vt_reg_value_traits", "_vt_reg_value_traits_persist")
    @log_exceptions
    def _vt_observe_vt_reg_value(self, change: ChangeType):
        """Update observers as they are changed.

        The register is a set of mappings of the HasTrait object to the name
        of the value to observe for change. The items that are monitored
        belong to various registers:
        * _vt_reg_value_traits
        * _vt_reg_value_traits_persist

        All pairs in the register monitor for changes and notify to the
        method _tw_reg_on_<REG NAME>_change, which may update the register
        and then pass the notification to `_vt_on_change` and then `on_change`
        which is available for overloading by subclasss definitions.
        """
        if change["name"] == "_vt_reg_value_traits":
            handler = self._vt_on_reg_value_traits_change
        elif change["name"] == "_vt_reg_value_traits_persist":
            handler = self._vt_on_value_traits_persist_change
        elif isinstance(change["owner"], _TypedTupleRegister):
            handler = change["owner"].change_handler
        else:
            msg = f"{change['name']}"
            raise NotImplementedError(msg)
        old = set() if change["old"] is Undefined else change["old"]
        new = change["new"]
        for obj, name in old.difference(new):
            with contextlib.suppress(Exception):
                obj.unobserve(handler, name)
        for obj, name in new.difference(old):
            obj.observe(handler, names=name)

    @classmethod
    def _get_observer_pairs(cls, obj: HasTraits, dotname: str) -> Iterator[tuple[HasTraits, str]]:
        """Generator to find all (obj,name) pairs."""
        parts = dotname.split(".")
        segments = len(parts)
        try:
            for i, n in enumerate(parts, 1):
                if n in obj._traits:
                    yield (obj, n)
                else:
                    msg = (
                        f'"{n}" is not a trait of {utils.fullname(obj)}\n '
                        "It must be defined as a trait if you want to observe it with "
                        f'value_traits. value_traits item = "{dotname}".'
                    )
                    raise TypeError(msg)
                if n in obj._trait_values:
                    obj = obj._trait_values[n]
                elif n in getattr(obj, "_InstanceHP", {}):
                    break
                else:
                    try:
                        # obj is not an instance of HasParent and/or n is not an InstanceHP trait
                        obj = getattr(obj, n)
                    except TraitError:
                        # No default - so okay to break
                        break
                if obj is None:
                    break
                if cls._AUTO_VALUE and i == segments and n != "value" and "value" in getattr(obj, "_traits", {}):
                    yield (obj, "value")
        except AttributeError:
            if not isinstance(obj, Bunched):
                raise

    @classmethod
    def _tuple_register(cls, tuplename: str):
        """Get the dict for the registered TypedInstanceTuple (trait) for the current
        class."""
        if tuplename not in cls._vt_tit_names:
            msg = (
                f"{tuplename=} is not a registered typed_instance_tuple "
                f"Register tuple names ={list(cls._vt_tit_names)}!"
            )
            raise KeyError(msg)
        return cls._vt_tit_names[tuplename]

    def _vt_update_reg_value_traits(self):
        pairs = set()
        if not self.discontinued:
            for dotname in self.value_traits:
                for pair in self._get_observer_pairs(self, dotname):
                    pairs.add(pair)
            self._vt_reg_value_traits = pairs

    def _vt_update_reg_value_traits_persist(self):
        pairs = set()
        if not self.discontinued:
            for dotname in self.value_traits_persist:
                for pair in self._get_observer_pairs(self, dotname):
                    pairs.add(pair)
            self._vt_reg_value_traits_persist = pairs

    def _vt_update_reg_tuples(self, tuplename):
        names = self._vt_tit_names[tuplename]["update_item_names"]
        items = getattr(self, tuplename)
        pairs = set()
        for obj in items:
            for dotname in names:
                for owner, n in self._get_observer_pairs(obj, dotname):
                    pairs.add((owner, n))
        self._vt_tuple_reg[tuplename].reg = pairs

    @log_exceptions
    def _vt_value_traits_observe(self, change: ChangeType):
        if mb.DEBUG_ENABLED and self._prohibited_value_traits.intersection(change["new"]):
            msg = f"A prohibited value trait has been detected: {self._prohibited_value_traits.intersection(change['new'])}"
            raise RuntimeError(msg)
        if change["name"] == "value_traits":
            self._vt_update_reg_value_traits()
        if change["name"] == "value_traits_persist":
            self._vt_update_reg_value_traits_persist()

    def _vt_tuple_on_change(
        self,
        change: ChangeType,
        tuplename: str,
        on_add: Callable,
        on_remove: Callable,
        _tuple_on_add: Callable,
        _tuple_on_remove: Callable,
    ):
        # Collect pairs and update register
        if self.discontinued:
            return
        self._vt_update_reg_tuples(tuplename)
        # Callbacks
        new = set(change["new"])
        old = set(change["old"] or ())
        if _tuple_on_remove or on_remove:
            for obj in old.difference(new):
                if _tuple_on_remove:
                    self._typed_tuple_do_callback(_tuple_on_remove, obj, tuplename, INTERNAL)
                if on_remove:
                    self._typed_tuple_do_callback(on_remove, obj, tuplename, EXTERNAL)
        if _tuple_on_add or on_add:
            for obj in new.difference(old):
                if _tuple_on_add:
                    self._typed_tuple_do_callback(_tuple_on_add, obj, tuplename, INTERNAL)
                if on_add:
                    self._typed_tuple_do_callback(on_add, obj, tuplename, EXTERNAL)
        # Share notification to on_change and update the value
        if change["name"] not in (*self.value_traits, *self.value_traits_persist):
            self._vt_on_change(change)

    def _typed_tuple_do_callback(self, callback: Callable, obj: ValueTraits, tuplename: str, mode: CallbackMode):
        """Callback specific to typed instance tuples. for on_change, on_add, on_remove.

        Will log an error on failure rather than raising it (except when debugging)
        """
        try:
            callback(self, obj) if mode is INTERNAL else callback(obj)
        except Exception as e:
            obj.on_error(e, f"Typed tuple callback '{tuplename}'")
            if mb.DEBUG_ENABLED:
                raise

    def _vt_on_reg_value_traits_change(self, change: ChangeType):
        if (isinstance(change["new"], HasTraits) or isinstance(change["old"], HasTraits)) and (
            change["new"] is not change["old"]
        ):
            self._vt_update_reg_value_traits()
        self._vt_on_change(change)

    def _vt_on_value_traits_persist_change(self, change: ChangeType):
        if (isinstance(change["new"], HasTraits) or isinstance(change["old"], HasTraits)) and (
            change["new"] is not change["old"]
        ):
            self._vt_update_reg_value_traits_persist()
        self._vt_on_change(change)

    def _vt_on_reg_tuples_change(self, change, traitname):
        if (isinstance(change["new"], HasTraits) or isinstance(change["old"], HasTraits)) and (
            change["new"] is not change["old"]
        ):
            self._vt_update_reg_tuples(traitname)
        self._vt_on_change(change)

    def _vt_on_change(self, change: ChangeType):
        """Emits changes."""
        if mb.DEBUG_ENABLED:
            self.log.debug(
                "\tCHANGE "  # noqa: G003
                + (f"ignored (context={self._ignore_change_cnt})" if self._ignore_change_cnt else "")
                + f"\t{change['owner'].__class__.__name__}.{change['name']}\t"
                f"{utils.fullname(change['old'])} →{utils.fullname(change['new'])}"
            )
        if self._ignore_change_cnt:
            return
        # `value` updated after "leaving context" (originally using context but only used here.)
        self.vt_updating = True
        self._vt_busy_updating_count = self._vt_busy_updating_count + 1
        try:
            self.on_change(change)
        except Exception as e:
            if self._vt_busy_updating_count == 1:
                self.on_error(e, "Change event error", change)
            raise
        finally:
            self._vt_busy_updating_count -= 1
            if not self._vt_busy_updating_count:
                self.vt_updating = False
                if self._vt_init_complete and not self.vt_validating:
                    self.set_trait("value", defaults.NO_VALUE)

    def _load_value(self, data: Literal[defaults._NoValue.token] | dict | Callable):
        if self.discontinued:
            return
        try:
            self.load_value(data)
        except Exception as e:
            self.on_error(e, "Error loading data", data)
            raise

    def add_value_traits(self, *names: str, delay: float | None = None):
        """Append names to value_traits.

        delay: if it is not None, it will be called with a delay.
            a delay = 0 is equivalent to `asyncio.call_soon`.
        """
        if delay is not None:
            utils.call_later(0, self.add_value_traits, *names)
            return
        self.set_trait("value_traits", (*self.value_traits, *names))

    def drop_value_traits(self, *names: str):
        """Remove to value_traits.

        value_traits are used for notifications. Dotted paths are permitted.
        """
        self.set_trait("value_traits", (v for v in self.value_traits if v not in names))

    def load_value(self, data: Literal[defaults._NoValue.token] | dict | Callable[[], dict] | pathlib.Path | str):
        if data is not defaults.NO_VALUE and data:
            while callable(data):
                data = data()
            if isinstance(data, str | pathlib.Path):
                data = ruamel.yaml.YAML(typ="safe").load(data)
            if not isinstance(data, dict):
                msg = f"Expected a dict but got a {data.__class__}."
                raise TypeError(msg)

            self.load_nested_attrs(obj=self, values=data, raise_errors=False, default_setter=self.setter)

    def get_value(self, dotname: str, default=None) -> Any:
        """Gets value by dotted name.

        If dottedname points to a HasTraits object with a value, the value will be
        returned. Uses utils.getattr_nested.

        (Callables will be evaluated).
        """
        return utils.getattr_nested(self, dotname, default=default)

    @staticmethod
    def getattr(obj, name, default=defaults.NO_VALUE):
        """Like getattr but will test and call if callable (recursively)."""
        val = getattr(obj, name, default) if not defaults.is_no_value(default) else getattr(obj, name)
        while callable(val):
            val = val()
        return val

    def to_dict(self, names: None | Iterable[str] = None, hastrait_value=True) -> dict[str, Any]:
        """A dict of dotted attribute names to the attribute.

        names:
        `dotted_attribute_name` to any current attribute.
        If None self.value_traits_persit is used.

        hastrait_value: Bool
            If True, will retrieve the values of HasTrait instances.
            False will pass the instance.
        """
        if names is None:
            names = self.value_traits_persist
        return {n: utils.getattr_nested(self, n, hastrait_value=hastrait_value) for n in names}

    _value = to_dict  # Alias provided to allow for easy overloading

    if TYPE_CHECKING:

        @overload
        def to_json(self) -> str: ...
        @overload
        def to_json(self, names: None | Iterable[str]) -> str: ...
        @overload
        def to_json(self, names: None | Iterable[str], option: int) -> str: ...
        @overload
        def to_json(self, names: None | Iterable[str], option: int, decode: Literal[False]) -> bytes: ...

    def to_json(
        self,
        names: None | Iterable[str] = None,
        option: int = orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_INDENT_2,
        decode=True,
    ) -> str | bytes:
        """Convert this object to json using orjson.dumps. names are the dotted names
        belonging to the object that are to be serialized.

        The default value traits are those set in the named tuple
        `value_traits_persist`.

        option: see: https://github.com/ijl/orjson for options

            eg: orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_INDENT_2

        decode: Decode the return value to a string instead of bytes
        """
        try:
            data = self.to_dict(names, hastrait_value=True)
        except TypeError:
            data = self.to_dict()
            if names:
                self.log.warning(f"Ignored {names=}", stack_info=True)
        try:
            data = orjson.dumps(data, default=json_default_converter, option=option)
            if decode:
                return data.decode()
        except TypeError:
            raise
        except Exception:
            return json.dumps(data, default=json_default_converter)
        else:
            return data

    def to_yaml(
        self, names: None | Iterable[str] = (), fs: AbstractFileSystem | None = None, path: str | None = None
    ) -> str:
        """Convert settings to yaml.
        path:
            if provided will write the the file using self.fs.
        """
        return to_yaml(self.to_dict(names=names), walkstring=True, path=path, fs=fs)  # type: ignore

    def on_change(self, change: ChangeType):
        """To overload:

        Main handler for monitored traits as defined in the list of value_traits.
        TypedInstanceTuples notifications are also delivered here.

        It is recommended to use the following system:

        ``` def on_change(self, change:Change):

            self._CLASS_on_change(change) ```

        Using super().on_change() should be avoided. Instead call directly the methods
        as required.
        """
        on_change = getattr(super(), "on_change", None)
        if callable(on_change):
            on_change(change)

    @classmethod
    def get_tuple_singleton_by(cls, tuplename: str) -> tuple:
        """Get the (combined) SINGLETON_BY of the trait/s registered for the trait of
        the class."""
        if tuplename not in cls._vt_tit_names:
            msg = (
                f"{tuplename=} is not a registered typed_instance_tuple "
                f"Register tuple names ={list(cls._vt_tit_names)}!"
            )
            raise KeyError(msg)
        return cls._tuple_register(tuplename)["SINGLETON_BY"]() or ()

    def get_tuple_obj(self, tuplename: str, add=True, **kwds):
        """Get an existing or create a new instance (if permitted) of the trait
        registered in the tuple for the current instance.
        tuplename: The attribute name of the TypedInstanceTuple.
        add: Whether to add new instances to the tuple.
        """
        new_update_inst = self._tuple_register(tuplename)["new_update_inst"]
        index = kwds.pop("index", None)
        obj = new_update_inst(self, kwds, index=index)
        if add:
            t = getattr(self, tuplename)  # type:tuple
            if obj not in t:
                self.set_trait(tuplename, (*t, obj))
        return obj
