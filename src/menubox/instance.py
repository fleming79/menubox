from __future__ import annotations

import inspect
import sys
import weakref
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Literal,
    NotRequired,
    Self,
    TypedDict,
    Unpack,
    cast,
    overload,
    override,
)

import ipylab.common
import traitlets
from ipywidgets import DOMWidget, Widget
from mergedeep import Strategy, merge

import menubox as mb
import menubox.hasparent as mhp
from menubox import utils
from menubox.defaults import ENABLE, NO_DEFAULT
from menubox.trait_types import SS, Bunched, GetWidgetsInputType, P, ReadOnly, S, T, W

if TYPE_CHECKING:
    from collections.abc import Callable

    from menubox.css import CSScls
    from menubox.defaults import NO_DEFAULT_TYPE


__all__ = ["InstanceHP", "instanceHP_wrapper"]


class IHPCreate(TypedDict, Generic[S, T]):
    name: str
    parent: S
    klass: type[T]
    kwgs: dict


class IHPSet(TypedDict, Generic[S, T]):
    name: str
    parent: S
    obj: T


class IHPChange(TypedDict, Generic[S, T]):
    name: str
    parent: S
    old: T | None
    new: T | None
    ihp: InstanceHP[S, T, Any]


class SetChildrenSettings(TypedDict):
    mode: Literal["monitor", "monitor_nametuple"]
    dottednames: NotRequired[tuple[str, ...]]  # 'monitor' `mode` only
    nametuple_name: NotRequired[str]  # 'monitor_nametuple' `mode` only


class IHPHookMappings(TypedDict, Generic[S, T]):
    set_parent: NotRequired[bool]
    add_css_class: NotRequired[str | tuple[str | CSScls, ...]]
    on_set: NotRequired[Callable[[IHPSet[S, T]], Any]]
    on_unset: NotRequired[Callable[[IHPSet[S, T]], Any]]
    on_replace_close: NotRequired[bool]
    remove_on_close: NotRequired[bool]
    set_children: NotRequired[Callable[[S], GetWidgetsInputType[T]] | SetChildrenSettings]
    value_changed: NotRequired[Callable[[IHPChange[S, T]], T | None]]


class InstanceHP(traitlets.TraitType[T, W], Generic[S, T, W]):
    """Descriptor for managing instances of a specific class as a trait.

    `InstanceHP` is a trait type that manages instances of a particular class.
    It handles instantiation, validation, and interaction with the managed
    instance, including setting parents, observing changes, and providing
    default values. It also supports plugin hooks for customization.
    The class provides a way to define and configure how instances of a class
    are created and managed as traits within a `HasParent` object. It supports
    lazy instantiation, default value loading, and allows customization through
    plugin hooks.
    Attributes:
        klass: The class to be managed. Can be a class type or a string
            representing the full path to the class.
        default_value: The default value for the trait. Defaults to None.
        allow_none: Whether None is a valid value for the trait. Defaults to True.
        read_only: Whether the trait is read-only. Defaults to True.
        load_default: Whether to load a default instance if no value is provided.
            Defaults to True.
        create: An optional callable that is used to create the instance.
        settings: A dictionary to store settings related to the instance.
        info_text: A property that returns a string describing the instance type.

    Type hints:
    -----------
    Option 1:
        Pass `cast(Self, 0)` as the first argument to enable type hinting
        access to the parent class.
    Option 2:
        Define both types on the class with InstanceHP[Self, Klass, SetType]
    """

    klass: type[T]
    default_value = None
    allow_none = False
    read_only = True
    load_default = True
    _change_hooks: ClassVar[dict[str, Callable[[IHPChange], None]]] = {}
    _close_observers: ClassVar[dict[InstanceHP, weakref.WeakKeyDictionary[mhp.HasParent[Any] | Widget, dict]]] = {}

    if TYPE_CHECKING:
        name: str  # type: ignore
        _hookmappings: IHPHookMappings[S, T]

        def __new__(
            cls,
            cast_self: S | int = 0,
            /,
            *,
            klass: type[T] | str,
            default: Callable[[IHPCreate[S, T]], T | None] | None = None,
            validate: Callable[[S, T | None], T | None] | None = None,
        ) -> InstanceHP[S, T, ReadOnly[Any]]: ...

    @override
    def __set__(self, obj: mhp.HasParent, value: W) -> None:  # type: ignore
        if self.read_only:
            msg = f'The "{self.name}" trait is read-only.'
            raise traitlets.TraitError(msg)
        if value is ENABLE:
            if obj._trait_values.get(self.name) is not None:
                return
            value = self.default(obj, {})  # type: ignore
        self.set(obj, value)  # type: ignore

    def __init__(
        self,
        cast_self: S | int = 0,
        /,
        *,
        klass: type[T] | str,
        default: Callable[[IHPCreate[S, T]], T | None] | None = None,
        validate: Callable[[S, T | None], T | None] | None = None,
    ) -> None:
        self._hookmappings = {}
        self._default = default
        self.validate = validate
        if not klass:
            msg = "klass must be specified"
            raise ValueError(msg)
        if isinstance(klass, str):
            if "." not in klass:
                msg = f"{klass=} must be passed with the full path to the class inside the module"
                raise ValueError(msg)
            self._klass = klass
        elif inspect.isclass(klass):
            self._klass = klass
        else:
            msg = f"{klass=} must be either a class,  or the full path to the class!"
            raise TypeError(msg)
        super().__init__()

    @property
    def info_text(self):  # type: ignore
        return f"an instance of `{self.klass.__qualname__}` {'or `None`' if self.allow_none else ''}"

    def __repr__(self):
        return f"<InstanceHP: {utils.fullname(self.this_class)}.{self.name}>"

    def __str__(self):
        return self.name

    def set(self, obj: S, value) -> None:  # type: ignore
        self.finalize()
        new_value = self._validate(obj, value)
        if self._set_parent and isinstance(value, mhp.HasParent):
            # Do this early in case the parent is invalid.
            value.parent = obj  # type: ignore
        try:
            old_value = obj._trait_values[self.name]
            if obj.SINGLE_BY and self.name in obj.SINGLE_BY and new_value not in obj.single_key:
                try:
                    raise_error = value != old_value
                except BaseException:
                    raise_error = True
                if raise_error:
                    msg = (
                        f"Changing {obj.__class__.__name__}.{self.name} is prohibited because it is in {obj.SINGLE_BY=}"
                    )
                    raise ValueError(msg)
        except KeyError:
            old_value = self.default_value

        obj._trait_values[self.name] = new_value
        try:
            silent = bool(old_value == new_value)
        except Exception:
            # if there is an error in comparing, default to notify
            silent = False
        if silent is not True:
            # we explicitly compare silent to True just in case the equality
            # comparison above returns something other than True/False
            try:
                self._value_changed(obj, old_value, new_value)
            except Exception as e:
                obj.on_error(e, f"Instance configuration error for {self!r}.")
            obj._notify_trait(self.name, old_value, new_value)

    def get(self, obj: S, cls: Any = None) -> T | None:  # type: ignore
        try:
            return obj._trait_values[self.name]  # type: ignore
        except KeyError:
            # Obtain the default.
            default = self.default(obj)

            # Using a context manager has a large runtime overhead, so we
            # write out the obj.cross_validation_lock call here.
            _cross_validation_lock = obj._cross_validation_lock
            try:
                obj._cross_validation_lock = True
                value = self._validate(obj, default)
            finally:
                obj._cross_validation_lock = _cross_validation_lock
            obj._trait_values[self.name] = value  # type: ignore
            dv = self.default_value
            try:
                silent = bool(value == dv)
            except Exception:
                # if there is an error in comparing, default to notify
                silent = False
            if silent is not True:
                self._value_changed(obj, dv, value)
                obj._notify_observers(Bunched(name=self.name, old=dv, new=value, owner=obj, type="change"))
            return value  # type: ignore
        except Exception as e:
            # This should never be reached.
            msg = "Unexpected error in TraitType: default value not set properly"
            raise traitlets.TraitError(msg) from e

    def finalize(self):
        """Finalizes the class associated with this instance.

        This method performs several steps:

        1.  Resolves the class: If `_klass` is a string, it imports the class.
        2.  Sets `self.klass` to the resolved class.
        3.  Updates hook mappings based on class properties and inheritance:
            -   If the class has `KEEP_ALIVE = True`, disables `on_replace_close`.
            -   Sets default values for `on_replace_close`, `set_parent`, and `remove_on_close`
            based on whether the class inherits from `HasParent` or `Widget`.
        4.  Sets the `_set_parent` attribute based on the `set_parent` hook mapping.
        """
        if hasattr(self, "klass"):
            return
        klass = self._klass if inspect.isclass(self._klass) else ipylab.common.import_item(self._klass)
        assert inspect.isclass(klass)  # noqa: S101
        self.klass = klass  # type: ignore
        m = self._hookmappings
        if getattr(klass, "KEEP_ALIVE", False):
            m["on_replace_close"] = False
        if "on_replace_close" not in m:
            if issubclass(klass, mhp.HasParent):
                m["on_replace_close"] = not klass.SINGLE_BY
            elif issubclass(klass, Widget) and "on_replace_close":
                m["on_replace_close"] = True
        if issubclass(klass, mhp.HasParent) and "set_parent" not in m:
            m["set_parent"] = True
        if "remove_on_close" not in m and issubclass(klass, mhp.HasParent | Widget):
            m["remove_on_close"] = True
        self._set_parent = m.get("set_parent", False)

    def default(self, parent: S, override: None | dict = None) -> T | None:  # type: ignore
        """Create an instance of the class.

        Args:
            parent: The parent object.
            override: A dictionary of keyword arguments to override the default keyword arguments.
        Returns:
            An instance of the class, or None if `allow_none` is True and `load_default` is False.
        Raises:
            RuntimeError: If both `load_default` and `allow_none` are False and the value is unset.
            Exception: If instance creation fails.
        """
        self.finalize()
        try:
            if not self.load_default and override is None:
                if self.allow_none:
                    return None
                msg = f"Both `load_default` and `allow_none` are `None` and the value is unset for {self!r}"
                raise RuntimeError(msg)  # noqa: TRY301
            kwgs = {"parent": parent} if self._set_parent else {}
            if override:
                kwgs = kwgs | override
            if default := self._default:
                return default(IHPCreate(parent=parent, name=self.name, klass=self.klass, kwgs=kwgs))
            return self.klass(**kwgs)

        except Exception as e:
            parent.on_error(e, f"Instance creation failed for {self!r}", self)
            raise

    def _validate(self, obj: S, value) -> T | None:
        if validate := self.validate:
            value = validate(obj, value)
        if value is None:
            if self.allow_none:
                return value
            msg = f"`None` is not allowed for {self!r}. Use `.configure(allow_none=True)` to permit it."
            raise traitlets.TraitError(msg)
        if isinstance(value, self.klass):  # type:ignore[arg-type]
            if obj._cross_validation_lock is False:
                value = self._cross_validate(obj, value)
            return value
        self.error(obj, value)  # noqa: RET503

    def _value_changed(self, parent: S, old: T | None, new: T | None):
        if new is None and old is None:
            return
        if hookmappings := self._hookmappings:
            change = IHPChange(name=self.name, parent=parent, old=old, new=new, ihp=self)
            for hookname in hookmappings:
                if hook := self._change_hooks.get(hookname):
                    try:
                        hook(change)
                    except Exception as e:
                        if "pytest" in sys.modules:
                            # If debugging import `pytest` to make this repeatable
                            raise
                        parent.on_error(e, f"Hook error for {self!r} {hook=}")

    def _on_obj_close(self, obj: S):
        if (old := obj._trait_values.pop(self.name, None)) is not self.default_value or old != self.default_value:
            self._value_changed(obj, old, self.default_value)  # type: ignore

    if TYPE_CHECKING:

        @overload
        def configure(
            self,
            *,
            allow_none: Literal[False],
            read_only: Literal[True],
            load_default: bool = True,
            default_value: NO_DEFAULT_TYPE | T = NO_DEFAULT,
        ) -> InstanceHP[S, T, ReadOnly[T]]: ...
        @overload
        def configure(
            self,
            *,
            allow_none: Literal[True],
            read_only: Literal[True],
            load_default: bool = True,
            default_value: NO_DEFAULT_TYPE | T | None = NO_DEFAULT,
        ) -> InstanceHP[S, T | None, ReadOnly[T]]: ...
        @overload
        def configure(
            self,
            *,
            allow_none: Literal[True],
            read_only: Literal[False],
            load_default: Literal[True] = ...,
            default_value: NO_DEFAULT_TYPE | T | None = NO_DEFAULT,
        ) -> InstanceHP[S, T | None, T | None]: ...
        @overload
        def configure(
            self,
            *,
            allow_none: Literal[True],
            read_only: Literal[False],
            load_default: Literal[False] = False,
            default_value: NO_DEFAULT_TYPE | T | None = NO_DEFAULT,
        ) -> InstanceHP[S, T | None, T | None]: ...

        @overload
        def configure(
            self,
            *,
            allow_none: Literal[False],
            read_only: Literal[False],
            load_default: bool = True,
            default_value: NO_DEFAULT_TYPE | T = NO_DEFAULT,
        ) -> InstanceHP[S, T, T]: ...
        @overload
        def configure(
            self,
            *,
            load_default: bool = ...,
            default_value: NO_DEFAULT_TYPE | T = NO_DEFAULT,
        ) -> InstanceHP[S, T, ReadOnly[T]]: ...

    def configure(
        self,
        *,
        allow_none: bool = False,
        read_only: bool = True,
        load_default=True,
        default_value: NO_DEFAULT_TYPE | T | None = NO_DEFAULT,
    ) -> (
        InstanceHP[S, T, T]
        | InstanceHP[S, T | None, ReadOnly[T]]
        | InstanceHP[S, T, ReadOnly]
        | InstanceHP[S, T | None, T | None]
    ):
        """Configures the instance with the provided settings.

        This method allows configuring the instance's behavior regarding read-only status,
        allowing None values, and loading default values.  It uses a builder pattern
        allowing chained calls.

        Args:
            read_only:  If True, the instance will be read-only. Defaults to True.
            allow_none: If True, None values are permitted. If NO_DEFAULT, defaults to not load_default.
            load_default: If True, default values are loaded. If NO_DEFAULT, the existing value is kept.
            default_value: A value to use instead of `default_value` (used when the trait is unset as old_value).

        Note:
            `default_value` is only used as the default with respect to the unset value. It is used for
            comparison when emitting changes and may be used as an the `old` value.

        Enabling/Disabling:
            When configured with `allow_none=True` you can use the methods `enable_ihp` and `disable_ihp` respectively.

            When configured with `allow_none=True, read_only=False` the trait can also be enabled/disabled by
            item assignment with the `ENABLE` token (from defaults) to enable and `None` to disable. Note however
            that the enable

            Because type hints are static, they will continue to reflect the configured state of the
            descriptor. You should always check the the trait is available before working with it.

        Item assignment in lambdas:
            Attribute assignment isn't permitted in lambda expressions instead, you should can use the
            methods to perform item assignments instead. To perform multiple ssignments in a lambda just
            make a tuple of item assignments.

            Assignment expressions are permitted, and can be useful to store intermediate values. Should
            you need to return a single result, simply access slice the tuple/list as required.

            - [lambda expressions](https://docs.python.org/3.13/reference/expressions.html#lambda)
            - [Assignment expressions](https://docs.python.org/3.13/reference/expressions.html#assignment-expressions)

        Returns:
            The instance itself (self), with updated configuration. The return type reflects whether None is allowed.
        """
        self.load_default = load_default
        self.allow_none = allow_none
        self.read_only = read_only
        if default_value is not NO_DEFAULT:
            self.default_value = default_value
        return self  # type: ignore

    def hooks(self, **kwgs: Unpack[IHPHookMappings[S, T]]) -> Self:
        """Configure what hooks to use when the instance value changes.

        Hooks are merged using a nested replace strategy.

        Additional custom hooks are also possible with the class method `register_change_hook`.

        Defaults
        --------
        * set_parent: True [HasParent]
        * on_replace_close: True [HasParent | Widget]

        Parameters
        ----------
        on_replace_close: Bool
            Close the previous instance if it is replaced.
            Note: HasParent will not close if its the property `KEEP_ALIVE` is True.
        allow_none :  bool
            Allow the value to be None.
        set_parent: Bool [True]
            Set the parent to the parent of the trait (HasParent).
        set_children: Callable[[S], utils.GetWidgetsInputType] | SetChildrenSettings
            Children are collected from the parent using `parent.get_widgets`.
            and passed as the keyword argument `children`= (<widget>,...) when creating a new instance.

            Additionally, if mode is 'monitor', the children will be updated as the state
            of the children is changed (including add/remove hide/show).
            If mode is 'monitor_nametuple', the children will be updated as the state
            of the children is changed (including add/remove hide/show).
            The children will be passed as a named tuple with the name specified in the
            `nametuple_name` field.
        add_css_class: str | tuple[str, ...] <DOMWidget **ONLY**>
            Class names to add to the instance. Useful for selectors such as context menus.
        remove_on_close: bool
            If True, the instance will be removed from the parent when the instance is closed.
        on_set: IHPChange
            A new value when it isn't None.
        on_unset: IHPChange
            An old value when it isn't None.
        """
        if kwgs:
            merge(self._hookmappings, kwgs, strategy=Strategy.REPLACE)  # type:ignore
        return self

    @classmethod
    def register_change_hook(cls, name: str, hook: Callable[[IHPChange], None], *, replace=False):
        if not replace and name in cls._change_hooks:
            msg = f"callback hook {name=} is already registered!"
            raise KeyError(msg)
        cls._change_hooks[name] = hook

    @classmethod
    def _remove_on_close_hook(cls, c: IHPChange[S, T]):
        if c["parent"].closed:
            return
        if c["ihp"] not in cls._close_observers:
            cls._close_observers[c["ihp"]] = weakref.WeakKeyDictionary()
        # value closed
        if (old_observer := cls._close_observers[c["ihp"]].pop(c["parent"], {})) and isinstance(
            c["old"], mhp.HasParent | Widget
        ):
            try:  # noqa: SIM105
                c["old"].unobserve(**old_observer)
            except ValueError:
                pass

        if isinstance(c["new"], mhp.HasParent | Widget):
            parent_ref = weakref.ref(c["parent"])
            inst = c["ihp"]

            def _observe_closed(change: mb.ChangeType):
                # If the c["parent"] has closed, remove it from c["parent"] if appropriate.
                parent = parent_ref()
                cname, value = change["name"], change["new"]
                if (
                    parent
                    and ((cname == "closed" and value) or (cname == "comm" and not value))
                    and parent._trait_values.get(inst.name) is change["owner"]
                ) and (old := parent._trait_values.pop(inst.name, None)):
                    inst._value_changed(parent, old, None)

            names = "closed" if isinstance(c["new"], mhp.HasParent) else "comm"
            c["new"].observe(_observe_closed, names)
            cls._close_observers[c["ihp"]][c["parent"]] = {"handler": _observe_closed, "names": names}

    @staticmethod
    def _on_replace_close_hook(c: IHPChange[S, T]):
        if c["ihp"]._hookmappings.get("on_replace_close") and isinstance(c["old"], Widget | mhp.HasParent):
            if mb.DEBUG_ENABLED:
                c["parent"].log.debug(
                    f"Closing replaced item `{c['parent'].__class__.__name__}.{c['ihp'].name}` {c['old'].__class__}"
                )
            c["old"].close()

    @staticmethod
    def _on_set_hook(c: IHPChange[S, T]):
        if c["new"] is not None and (on_set := c["ihp"]._hookmappings.get("on_set")):
            on_set(IHPSet(name=c["ihp"].name, parent=c["parent"], obj=c["new"]))

    @staticmethod
    def _on_unset_hook(c: IHPChange[S, T]):
        if c["old"] is not None and (on_unset := c["ihp"]._hookmappings.get("on_unset")):
            on_unset(IHPSet(name=c["ihp"].name, parent=c["parent"], obj=c["old"]))

    @staticmethod
    def _add_css_class_hook(c: IHPChange[S, T]):
        if add_css_class := c["ihp"]._hookmappings.get("add_css_class"):
            for cn in utils.iterflatten(add_css_class):
                if isinstance(c["new"], DOMWidget):
                    c["new"].add_class(cn)
                if isinstance(c["old"], DOMWidget):
                    c["old"].remove_class(cn)

    @staticmethod
    def _set_parent_hook(c: IHPChange[S, T]):
        if c["ihp"]._hookmappings.get("set_parent"):
            if isinstance(c["old"], mhp.HasParent) and getattr(c["old"], "parent", None) is c["parent"]:
                c["old"].parent = None  # type: ignore
            if isinstance(c["new"], mhp.HasParent) and not c["parent"].closed:
                c["new"].parent = c["parent"]  # type: ignore

    @staticmethod
    def _set_children_hook(c: IHPChange[S, T]):
        import menubox.children_setter

        if c["new"] is not None and (children := c["ihp"]._hookmappings.get("set_children")):
            if isinstance(children, dict):
                val = {} | children
                val.pop("mode")
                menubox.children_setter.ChildrenSetter(parent=c["parent"], name=c["ihp"].name, value=val)
            else:
                children = c["parent"].get_widgets(children, skip_hidden=False, show=True)  # type: ignore
                c["new"].set_trait("children", children)  # type: ignore

    @staticmethod
    def _value_changed_hook(c: IHPChange[S, T]):
        if value_changed := c["ihp"]._hookmappings.get("value_changed"):
            value_changed(c)

    @staticmethod
    def _validate_hook(c: IHPChange[S, T]):
        if value_changed := c["ihp"]._hookmappings.get("value_changed"):
            value_changed(c)

    @override
    def class_init(self, cls, name):
        try:
            cls._InstanceHP[name] = self  # type: ignore # type: type[HasParent]
        except AttributeError:
            msg = "InstanceHP can only be used as a trait in HasParent subclasses!"
            raise AttributeError(msg) from None
        return super().class_init(cls, name)

    @classmethod
    def _register_default_hooks(cls):
        for cb in (
            cls._on_replace_close_hook,
            cls._set_parent_hook,
            cls._remove_on_close_hook,
            cls._on_set_hook,
            cls._on_unset_hook,
            cls._add_css_class_hook,
            cls._set_children_hook,
            cls._value_changed_hook,
        ):
            cls.register_change_hook(cb.__name__.removesuffix("hook").strip("_"), cb)


InstanceHP._register_default_hooks()


def instanceHP_wrapper(
    klass: Callable[P, T] | str,
    /,
    *,
    defaults: None | dict[str, Any] = None,
    strategy=Strategy.REPLACE,
    tags: None | dict[str, Any] = None,
    **kwargs: Unpack[IHPHookMappings[mhp.HasParent, T]],
):
    """Wraps the InstanceHP trait for use withmhp. HasParent classes.

    This function creates a factory that returns an InstanceHP trait,
    configured with the specified settings. It's designed to be used
    when adding a trait to a new subclass ofmhp. HasParent.
    Args:
        klass: The class or a string representation of the class to be instantiated by the InstanceHP trait.
        defaults: A dictionary of default keyword arguments to be passed to the class constructor.
        strategy: The merging strategy to use when combining defaults with instance-specific keyword arguments.
                  Defaults to Strategy.REPLACE.
        tags: A dictionary of tags to be applied to the InstanceHP trait.
        **kwargs: Additional keyword arguments to be passed to the InstanceHP trait's configure method.
    Returns:
        A factory function that, when called, returns an InstanceHP trait instance.  The factory
        function accepts *args and **kwgs which are passed to the constructor of `klass` when the
        trait's default value is requested.
    Usage:
        Use this function to add an InstanceHP trait to a class that inherits frommhp. HasParent.
        The returned factory should be assigned as a class-level attribute.  When the trait
        is accessed for the first time on an instance of the class, the InstanceHP trait will
        be instantiated and configured.
    """

    defaults_ = merge({}, defaults) if defaults else {}
    tags = dict(tags) if tags else {}  # type: ignore

    def instanceHP_factory(cast_self: SS | None = None, /, *args: P.args, **kwgs: P.kwargs) -> InstanceHP[SS, T, T]:  # noqa: ARG001
        """Returns an InstanceHP[klass] trait.

        Use this to add a trait to new subclass ofmhp. HasParent.

        Specify *args and **kwgs to pass when creating the 'default' (when the trait default is requested).

        cast_self: Provided specifically for type checking. use: `cast(Self, 0)`

        Follow the link (ctrl + click): function-> klass to see the class definition and what *args and **kwargs are available.
        """
        if defaults_:
            kwgs = merge({}, defaults_, kwgs, strategy=strategy)  # type: ignore
        instance = InstanceHP(klass=klass, default=lambda c: c["klass"](*args, **kwgs | c["kwgs"]))  # type: ignore
        if kwargs:
            instance.hooks(**kwargs)  # type: ignore
        if tags:
            instance.tag(**tags)
        return cast(InstanceHP[SS, T, T], instance)

    return instanceHP_factory
