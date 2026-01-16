from __future__ import annotations

import contextlib
import enum
import inspect
import sys
import typing
import weakref
from types import UnionType
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

import traitlets
from async_kernel.common import import_item
from ipywidgets import DOMWidget, Widget
from mergedeep import Strategy, merge

import menubox as mb
import menubox.hasparent as mhp
from menubox import utils
from menubox.defaults import NO_DEFAULT
from menubox.trait_types import SS, Bunched, GetWidgetsInputType, P, ReadOnly, S, T, W

if TYPE_CHECKING:
    from collections.abc import Callable

    from menubox.css import CSScls
    from menubox.defaults import NO_DEFAULT_TYPE


__all__ = ["InstanceHP", "instanceHP_wrapper"]


class IHPMode(enum.IntEnum):
    """The configured modes for the Instance HP instance.

    `XCRN` - X is a common prefix. Underscores indicate the setting is disabled.

    - `C` : **load_default** - call the `default` function passed at initialization. If not enabled, `default_value` is returned.
    - `R` : **read_only** - configure as read-only.
    - `N` : **allow_none** - configure as allow none.

    The letters are code for enabling of feature. If the letter is not shown
    in that position, it is the disabled mode.
    """

    X___ = 0  #       load_default
    XL__ = 1  #       load_default
    X__N = 2  #       allow_none
    X_R_ = 4  #       read_only
    XL_N = 1 | 2  #   load_default - allow_none
    XLR_ = 1 | 4  #   load_default - read_only
    X_RN = 2 | 4  #   read_only - allow_none
    XLRN = 1 | 2 | 4  # load_default - read_only - allow_none


class IHPCreate(TypedDict, Generic[S, T]):
    name: str
    owner: S
    klass: type[T]
    kwgs: dict


class IHPSet(TypedDict, Generic[S, T]):
    name: str
    owner: S
    obj: T


class IHPChange(TypedDict, Generic[S, T]):
    name: str
    owner: S
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
    set_children: NotRequired[
        Callable[[S], GetWidgetsInputType[T]] | SetChildrenSettings
    ]
    value_changed: NotRequired[Callable[[IHPChange[S, T]], Any]]


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
        load_default: Whether to call the `default` instance when retrieving an unset value.
            Defaults to True.
        create: An optional callable that is used to create the instance.
        settings: A dictionary to store settings related to the instance.
        info_text: A property that returns a string describing the instance type.
        `co_`: cast `Self` for improved type hints.

    Type hints:
    -----------
    Option 1:
        Pass `co_=cast(Self, 0)` during init to provide extended type hinting for 'owner'.
    Option 2:
        Define both types on the class with `InstanceHP[Self, Getter, Setter]`
        ` `Self` : Provides for introspection on lambda methods for safer type hinting.
        - `Getter`: Is provides typing when retrieving the attribute
        - `Setter`: Allows to define the types that can be used for setting. Notably,
            the type can be wrapped with `ReadOnly` to show when the trait is read only.
    """

    klass: type[T]
    _default_override = None
    _type = None
    validate = None
    default_value = None
    _change_hooks: ClassVar[dict[str, Callable[[IHPChange], None]]] = {}
    _close_observers: ClassVar[
        dict[InstanceHP, weakref.WeakKeyDictionary[mhp.HasParent[Any] | Widget, dict]]
    ] = {}

    if TYPE_CHECKING:
        name: str  # pyright: ignore[reportIncompatibleVariableOverride]
        _hookmappings: IHPHookMappings[S, T]

        @overload
        def __new__(  # pyright: ignore[reportNoOverloadImplementation]
            cls,
            klass: UnionType,
            default: Callable[[IHPCreate[S, T]], T],
            *,
            validate: Callable[[S, T | Any], T] | NO_DEFAULT_TYPE = ...,
            default_value: NO_DEFAULT_TYPE | T | None = ...,
            co_: S = ...,
        ) -> InstanceHP[S, T, ReadOnly[T]]: ...
        @overload
        def __new__(
            cls,
            klass: type[T] | str,
            default: Callable[[IHPCreate[S, T]], T] | NO_DEFAULT_TYPE = ...,
            *,
            validate: Callable[[S, T | Any], T] | NO_DEFAULT_TYPE = ...,
            default_value: NO_DEFAULT_TYPE | T | None = NO_DEFAULT,
            co_: S = ...,
        ) -> InstanceHP[S, T, ReadOnly[T]]: ...

    def __set__(self, obj: mhp.HasParent, value: W) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.read_only:
            msg = f'The "{self!r}" is read-only.'
            raise traitlets.TraitError(msg)
        self.set(obj, value)  # pyright: ignore[reportArgumentType]

    def __init__(
        self,
        klass: type[T] | str | UnionType,
        default: Callable[[IHPCreate[S, T]], T] | NO_DEFAULT_TYPE = NO_DEFAULT,
        *,
        validate: Callable[[S, T | Any], T] | NO_DEFAULT_TYPE = NO_DEFAULT,
        default_value: NO_DEFAULT_TYPE | T | None = NO_DEFAULT,
        co_: S | Any = None,
    ) -> None:
        self._hookmappings = {}
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
        elif typing.get_origin(klass) in [typing.Union, UnionType]:
            self._type = klass
            if default is NO_DEFAULT:
                msg = "default must be provided when klass is specified as a union"
                raise TypeError(msg)
        else:
            msg = f"{klass=} must be either a class,  or the full path to the class!"
            raise TypeError(msg)
        super().__init__()
        self.configure(default_value=default_value, default=default, validate=validate)

    @property
    def info_text(self):  # pyright: ignore[reportIncompatibleVariableOverride]
        self.finalize()
        return f"an instance of `{self.klass.__qualname__}` {'or `None`' if self.allow_none else ''}"

    def __repr__(self):
        return f"<{self.__class__.__name__}: {utils.fullname(self.this_class)}.{self.name}>"

    def __str__(self):
        return self.name

    if TYPE_CHECKING:

        @overload
        def configure(
            self,
            mode: Literal[IHPMode.XLR_] = ...,
            /,
            *,
            default_value: NO_DEFAULT_TYPE | T | None = ...,
            default: Callable[[IHPCreate[S, T]], T] | NO_DEFAULT_TYPE = ...,
            validate: Callable[[S, T | Any], T] | NO_DEFAULT_TYPE = ...,
        ) -> InstanceHP[S, T, ReadOnly[T]]: ...

        @overload
        def configure(
            self,
            mode: Literal[IHPMode.X_R_,],
            /,
            *,
            default_value: NO_DEFAULT_TYPE | T = ...,
            default: Callable[[IHPCreate[S, T]], T] | NO_DEFAULT_TYPE = ...,
            validate: Callable[[S, T | Any], T] | NO_DEFAULT_TYPE = ...,
        ) -> InstanceHP[S, T, ReadOnly[T]]: ...

        @overload
        def configure(
            self,
            mode: Literal[IHPMode.XL__, IHPMode.X___],
            /,
            *,
            default_value: NO_DEFAULT_TYPE | T = ...,
            default: Callable[[IHPCreate[S, T]], T] | NO_DEFAULT_TYPE = ...,
            validate: Callable[[S, T | Any], T] | NO_DEFAULT_TYPE = ...,
        ) -> InstanceHP[S, T, T]: ...

        @overload
        def configure(
            self,
            mode: Literal[IHPMode.X__N, IHPMode.XL_N],
            /,
            *,
            default_value: NO_DEFAULT_TYPE | T | None = ...,
            default: Callable[[IHPCreate[S, T]], T | None] | NO_DEFAULT_TYPE = ...,
            validate: Callable[[S, T | Any], T | None] | NO_DEFAULT_TYPE = ...,
        ) -> InstanceHP[S, T | None, T | None]: ...

        @overload
        def configure(
            self,
            mode: Literal[IHPMode.XLRN, IHPMode.X_RN],
            /,
            *,
            default_value: NO_DEFAULT_TYPE | T | None = ...,
            default: Callable[[IHPCreate[S, T]], T | None] | NO_DEFAULT_TYPE = ...,
            validate: Callable[[S, T | Any], T | None] | NO_DEFAULT_TYPE = ...,
        ) -> InstanceHP[S, T | None, ReadOnly[T | None]]: ...

    def configure(
        self,
        mode: IHPMode = IHPMode.XLR_,
        /,
        *,
        default_value: T | None | NO_DEFAULT_TYPE = NO_DEFAULT,
        default: Callable[[IHPCreate[S, T]], T | None] | NO_DEFAULT_TYPE = NO_DEFAULT,
        validate: Callable[[S, T | None], T | None] | NO_DEFAULT_TYPE = NO_DEFAULT,
    ) -> (
        InstanceHP[S, T, T]
        | InstanceHP[S, T, ReadOnly]
        | InstanceHP[S, T | None, T | None]
        | InstanceHP[S, T | None, ReadOnly[T]]
        | InstanceHP[S, T | None, ReadOnly[T | None]]
    ):
        """Configures the instance with the provided settings.

        This method allows configuring the instance's behavior regarding read-only status,
        allowing None values, and loading default values.  It uses a builder pattern
        allowing chained calls.

        When the option `load_default` is unset; default_value will be used as the default, except
        if  when explicitly enabled as described below.

        Enabling/Disabling:
            When configured with `allow_none` you can use the methods `enable_ihp` and `disable_ihp` respectively.

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
        self.load_default = bool(mode & IHPMode.XL__)
        self.read_only = bool(mode & IHPMode.X_R_)
        self.allow_none = bool(mode & IHPMode.X__N)
        if default is not NO_DEFAULT:
            self._default_override = default
        if default_value is not NO_DEFAULT:
            self.default_value = default_value
        if validate is not NO_DEFAULT:
            self.validate = validate
        return self  # pyright: ignore[reportReturnType]

    def set(self, obj: S, value) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self.finalize()
        new_value = self._validate(obj, value)
        if self._set_parent and isinstance(value, mhp.HasParent):
            # Do this early in case the parent is invalid.
            value.parent = obj
        try:
            old_value = obj._trait_values[self.name]
            if (
                obj.SINGLE_BY
                and self.name in obj.SINGLE_BY
                and new_value not in obj.single_key
            ):
                try:
                    raise_error = value != old_value
                except BaseException:
                    raise_error = True
                if raise_error:
                    msg = f"Changing {obj.__class__.__name__}.{self.name} is prohibited because it is in {obj.SINGLE_BY=}"
                    raise ValueError(msg)
        except KeyError:
            old_value = self.default_value
        obj._trait_values[self.name] = new_value
        if not obj.check_equality(old_value, new_value):
            change = Bunched(
                name=self.name,
                old=old_value,
                new=new_value,
                owner=obj,
                type="change",
                ihp=self,
            )
            try:
                self._value_changed(cast("IHPChange", change))
            except Exception as e:
                obj.on_error(e, f"Instance configuration error for {self!r}.")
            obj._notify_trait(self.name, old_value, new_value)

    def get(self, obj: S, cls: Any = None) -> T | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        try:
            return obj._trait_values[self.name]
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
            obj._trait_values[self.name] = value
            dv = self.default_value
            if not obj.check_equality(value, dv):
                change = Bunched(
                    name=self.name,
                    old=dv,
                    new=value,
                    owner=obj,
                    type="change",
                    ihp=self,
                )
                self._value_changed(cast("IHPChange", change))
                obj._notify_observers(change)
            return value
        except Exception as e:
            # This should never be reached.
            msg = "Unexpected error in TraitType: default value not set properly"
            raise traitlets.TraitError(msg) from e

    def finalize(self) -> Self:
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
            return self
        m = self._hookmappings
        if self._type:
            self.klass = object  # pyright: ignore[reportAttributeAccessIssue]
        else:
            klass = (
                self._klass
                if inspect.isclass(self._klass)
                else import_item(self._klass)
            )
            assert inspect.isclass(klass)
            self.klass = klass  # pyright: ignore[reportAttributeAccessIssue]
            self._type = klass
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
        return self

    def default(self, owner: S, override: None | dict = None) -> T | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Create an instance of the class.

        Args:
            owner: The owning object.
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
                return self.default_value
            kwgs = {"parent": owner} if self._set_parent else {}
            if override:
                kwgs = kwgs | override
            if default := self._default_override:
                return default(
                    IHPCreate(owner=owner, name=self.name, klass=self.klass, kwgs=kwgs)
                )
            return self.klass(**kwgs)

        except Exception as e:
            with contextlib.suppress(Exception):
                owner.on_error(e, f"Instance creation failed for {self!r}", self)
            raise

    def _validate(self, obj: S, value) -> T | None:
        self.finalize()
        if value is None and self.allow_none:
            return value
        if validate := self.validate:
            return validate(obj, value)
        if isinstance(value, self._type):  # pyright: ignore[reportArgumentType, reportUnusedExpression]
            if obj._cross_validation_lock is False:
                value = self._cross_validate(obj, value)
            return value
        self.error(obj, value)
        raise ValueError

    def _value_changed(self, change: IHPChange[S, T]):
        if hookmappings := self._hookmappings:
            for hookname in hookmappings:
                if hook := self._change_hooks.get(hookname):
                    try:
                        hook(change)
                    except Exception as e:
                        if "pytest" in sys.modules:
                            # If debugging import `pytest` to make this repeatable
                            raise
                        change["owner"].on_error(e, f"Hook error for {self!r} {hook=}")

    def _on_obj_close(self, obj: S):
        if (
            old := obj._trait_values.pop(self.name, None)
        ) is not self.default_value or old != self.default_value:
            change = Bunched(
                name=self.name,
                old=old,
                new=self.default_value,
                owner=obj,
                type="change",
                ihp=self,
            )
            self._value_changed(cast("IHPChange", change))

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
            merge(self._hookmappings, kwgs, strategy=Strategy.REPLACE)  # pyright: ignore[reportArgumentType]
        return self

    @classmethod
    def register_change_hook(
        cls, name: str, hook: Callable[[IHPChange], None], *, replace=False
    ):
        if not replace and name in cls._change_hooks:
            msg = f"callback hook {name=} is already registered!"
            raise KeyError(msg)
        cls._change_hooks[name] = hook

    @classmethod
    def _remove_on_close_hook(cls, c: IHPChange[S, T]):
        if c["owner"].closed:
            return
        if c["ihp"] not in cls._close_observers:
            cls._close_observers[c["ihp"]] = weakref.WeakKeyDictionary()
        # value closed
        if (
            old_observer := cls._close_observers[c["ihp"]].pop(c["owner"], {})
        ) and isinstance(c["old"], mhp.HasParent | Widget):
            try:
                c["old"].unobserve(**old_observer)
            except ValueError:
                pass

        if isinstance(c["new"], mhp.HasParent | Widget):
            owner_ref = weakref.ref(c["owner"])
            ihp = c["ihp"]

            def _observe_closed(change: mb.ChangeType):
                # If the c["owner"] has closed, remove it from c["owner"] if appropriate.
                owner = owner_ref()
                cname, value = change["name"], change["new"]
                if (
                    owner
                    and (
                        (cname == "closed" and value) or (cname == "comm" and not value)
                    )
                    and owner._trait_values.get(ihp.name) is change["owner"]
                ) and (old := owner._trait_values.pop(ihp.name, None)):
                    change_ = Bunched(
                        name=ihp.name,
                        old=old,
                        new=None,
                        owner=owner,
                        type="change",
                        ihp=ihp,
                    )
                    ihp._value_changed(cast("IHPChange", change_))

            names = "closed" if isinstance(c["new"], mhp.HasParent) else "comm"
            c["new"].observe(_observe_closed, names)
            cls._close_observers[c["ihp"]][c["owner"]] = {
                "handler": _observe_closed,
                "names": names,
            }

    @staticmethod
    def _on_replace_close_hook(c: IHPChange[S, T]):
        if (
            c["ihp"]._hookmappings.get("on_replace_close")
            and isinstance(c["old"], Widget | mhp.HasParent)
            and not getattr(c["old"], "KEEP_ALIVE", False)
        ):
            if mb.DEBUG_ENABLED:
                c["owner"].log.debug(
                    f"Closing replaced item `{c['owner'].__class__.__name__}.{c['ihp'].name}` {c['old'].__class__}"
                )
            c["old"].close()

    @staticmethod
    def _on_set_hook(c: IHPChange[S, T]):
        if c["owner"].closed:
            return
        if c["new"] is not None and (on_set := c["ihp"]._hookmappings.get("on_set")):
            on_set(IHPSet(name=c["ihp"].name, owner=c["owner"], obj=c["new"]))

    @staticmethod
    def _on_unset_hook(c: IHPChange[S, T]):
        if c["owner"].closed:
            return
        if c["old"] is not None and (
            on_unset := c["ihp"]._hookmappings.get("on_unset")
        ):
            on_unset(IHPSet(name=c["ihp"].name, owner=c["owner"], obj=c["old"]))

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
        if (not c["owner"].closed) and c["ihp"]._hookmappings.get("set_parent"):
            if (
                isinstance(c["old"], mhp.HasParent)
                and getattr(c["old"], "parent", None) is c["owner"]
            ):
                c["old"].parent = None
            if isinstance(c["new"], mhp.HasParent) and not c["owner"].closed:
                c["new"].parent = c["owner"]

    @staticmethod
    def _set_children_hook(c: IHPChange[S, T]):
        import menubox.children_setter

        if c["owner"].closed:
            return
        if c["new"] is not None and (
            children := c["ihp"]._hookmappings.get("set_children")
        ):
            if isinstance(children, dict):
                val = {} | children
                val.pop("mode")
                menubox.children_setter.ChildrenSetter(
                    parent=c["owner"], name=c["ihp"].name, value=val
                )
            else:
                children = c["owner"].get_widgets(
                    children, skip_hidden=False, show=True
                )
                c["new"].set_trait("children", children)  # pyright: ignore[reportAttributeAccessIssue]

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
        super().class_init(cls, name)
        try:
            cls._InstanceHP[name] = self  # pyright: ignore[reportAttributeAccessIssue]
            if (not self.load_default) and (
                (self.default_value is not None) or self.allow_none
            ):
                # Provide static values to bypass unnecessary default calls.
                cls._static_immutable_initial_values[name] = self.default_value
        except AttributeError:
            msg = "InstanceHP can only be used as a trait in HasParent subclasses!"
            raise AttributeError(msg) from None

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
    **hooks: Unpack[IHPHookMappings[mhp.HasParent, T]],
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
        **hooks: Additional keyword arguments to be passed to the InstanceHP trait's configure method.
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
    tags = dict(tags) if tags else {}

    def instanceHP_factory(
        co_: SS | Any = None,
        /,
        *args: P.args,
        **kwgs: P.kwargs,
    ) -> InstanceHP[SS, T, ReadOnly[T]]:
        """Returns an InstanceHP[klass] trait.

        Use this to add a trait to new subclass ofmhp. HasParent.

        Specify *args and **kwgs to pass when creating the 'default' (when the trait default is requested).

        cast: Provided specifically for type checking. use: `c(Self, c)`

        Follow the link (ctrl + click): function-> klass to see the class definition and what *args and **kwargs are available.
        """
        if defaults_:
            kwgs = merge({}, defaults_, kwgs, strategy=strategy)  # pyright: ignore[reportAssignmentType]
        instance = InstanceHP(
            klass,  # pyright: ignore[reportCallIssue, reportArgumentType]
            lambda c: c["klass"](*args, **kwgs | c["kwgs"]),
            co_=co_,
        )
        if hooks:
            instance.hooks(**hooks)
        if tags:
            instance.tag(**tags)
        return instance

    return instanceHP_factory
