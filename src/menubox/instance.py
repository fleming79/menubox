from __future__ import annotations

import asyncio
import contextlib
import inspect
import weakref
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Literal,
    NotRequired,
    ParamSpec,
    Self,
    TypedDict,
    TypeVar,
    Unpack,
    overload,
)

import ipywidgets as ipw
import traitlets
from mergedeep import Strategy, merge

import menubox as mb
from menubox import mb_async, utils
from menubox.hasparent import HasParent
from menubox.trait_types import Bunched

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable


__all__ = ["InstanceHP", "instanceHP_wrapper"]


T = TypeVar("T")
P = ParamSpec("P")


class IHPCreate(Generic[T], TypedDict):
    name: str
    parent: HasParent
    klass: type[T]
    args: tuple
    kwgs: dict


class IHPChange(Generic[T], TypedDict):
    name: str
    parent: HasParent
    obj: T

class ChildrenDict(TypedDict):
    dottednames: tuple[str, ...]
    mode: Literal["monitor"]

class IHPSettings(Generic[T], TypedDict):
    load_default: NotRequired[bool]
    allow_none: NotRequired[bool]
    read_only: NotRequired[bool]
    set_parent: NotRequired[bool]
    add_css_class: NotRequired[str | tuple[str, ...]]
    create: NotRequired[str | Callable[[IHPCreate[T]], T]]
    change_new: NotRequired[str | Callable[[IHPChange[T]], None]]
    change_old: NotRequired[str | Callable[[IHPChange[T]], None]]
    dynamic_kwgs: NotRequired[dict[str, Any]]
    set_attrs: NotRequired[dict[str, Any]]
    dlink: NotRequired[IHPDlinkType | tuple[IHPDlinkType, ...]]
    on_click: NotRequired[str | Callable[[ipw.Button], Awaitable | None]]
    on_replace_close: NotRequired[bool]
    children: NotRequired[ChildrenDict | tuple[utils.GetWidgetsInputType, ...]]


class IHPDlinkType(TypedDict):
    """A TypedDict template to use with `InstanceHP.configure`."""

    source: tuple[str, str]  # Dotted name of HasTraits object relative to parent, trait name
    target: str  # The trait name of the Instance to dlink
    transform: NotRequired[Callable[[Any], Any]]


class InstanceHP(traitlets.ClassBasedTraitType, Generic[T]):
    default_value: None = None
    _klass: type[T] | None = None
    _default_settings: ClassVar[IHPSettings] = {
        "load_default": True,
        "allow_none": False,
        "read_only": True,
        "set_parent": True,
        "on_click": "button_clicked",
        "on_replace_close": True,
    }

    if TYPE_CHECKING:
        name: str  # type: ignore
        settings: IHPSettings[T]

        @overload
        def __get__(self, obj: Any, cls: type[HasParent]) -> T: ...  # type: ignore

    def class_init(self, cls, name):
        if issubclass(cls, HasParent):
            cls._InstanceHP[name] = self  # type: ignore # Register
        else:
            msg = (
                f"Setting {cls.__qualname__}.{name} = InstanceHP(...) is invalid "
                f"because {cls} is not a subclass of HasParent."
            )
            raise TypeError(msg)
        return super().class_init(cls, name)

    def __init__(self, klass: type[T] | str, *args, **kwgs: Any) -> None:
        """InstanceHP is an Instance type class  to spawn the instance of
        `klass(*args, **kwargs)` in the `HasParent` (parent) object.

        This class replaces `traitlets.Instance` providing the necessary customisation
        to simplify construnction cutting the need to define "default" decorators by
        99%. Notably, 'parent' is inserted into **kwargs for `HasParent` subclasses
        (configurable with the `configure` method).

        It's design is analogous to functools.partial such that *args and **kwgs are
        passed to the klass during instantion along with parent (if relevant). Default
        settings will load the 'default' but can also be overridden with the `configure` method.

        Parameters
        ----------
        klass : str | HasParent | object
            The class that forms the basis for the trait.  Class names
            can also be specified using the name of the class as a string.
            If the string contains a dot `.` It will be resolved.
            Else it is assumed to be an subclass of `HasParent`.
        *args
            Positional args passed to klass default.
        **kwgs
            Extra kwargs passed to to klass default.

        `configure`
        ----
        See also .configure for further detail.

        """
        if isinstance(klass, str):
            if "." not in klass:
                msg = f"{klass=} must be passed with the full path to the class inside the module"
                raise ValueError(msg)
            self.klass_name = klass
        elif inspect.isclass(klass):
            self._klass = klass
            self.klass_name = f"{klass.__module__}.{klass.__qualname__}"
        elif (args_ := getattr(klass, "__args__", None)) and "." in args_[0]:
            self.klass_name = args_[0]
        else:
            msg = f"{klass=} must be either a class, type['full.name.to.Class'] or the full path to the class!"
            raise TypeError(msg)
        if "parent" in kwgs:
            msg = "`parent`is an invalid argument. Use the `set_parent` tag instead."
            raise ValueError(msg)
        self.settings = self._default_settings.copy()
        super().__init__()
        self.args = args
        self.kwgs = kwgs
        self._close_observers: weakref.WeakKeyDictionary[HasParent, dict] = weakref.WeakKeyDictionary()

    @property
    def klass(self) -> type[T]:
        if not self._klass:
            self._klass = utils.import_item(self.klass_name)
            assert self._klass  # noqa: S101
        return self._klass

    @property
    def allow_none(self):  # type: ignore
        return self.settings["allow_none"]  # type: ignore

    @property
    def read_only(self):  # type: ignore
        return self.settings["read_only"]  # type: ignore

    @property
    def info_text(self):  # type: ignore
        return f"an instance of `{self.klass.__qualname__}` {'or `None`' if self.allow_none else ''}"

    @property
    def load_default(self):
        return self.settings["load_default"]  # type: ignore

    @property
    def set_parent(self):
        return self.settings["set_parent"]  # type: ignore

    def set(self, obj: HasParent, value) -> None:  # type: ignore
        if isinstance(value, dict) and self.klass_name:
            value = self.default(obj, value)
        new_value = self._validate(obj, value)
        if isinstance(value, HasParent) and self.set_parent:
            # Do this early in case the parent is invalid.
            value.parent = obj
        try:
            old_value = obj._trait_values[self.name]
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
                obj.on_error(e, "Instance configuration error.")
            obj._notify_trait(self.name, old_value, new_value)

    def get(self, obj: HasParent, cls: Any = None) -> T | None:  # type: ignore
        try:
            value: T | None = obj._trait_values[self.name]  # type: ignore
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
            self._value_changed(obj, None, value)
            obj._notify_observers(Bunched(name=self.name, old=None, new=value, owner=obj, type="change"))
            return value  # type: ignore
        except Exception as e:
            # This should never be reached.
            msg = "Unexpected error in TraitType: default value not set properly"
            raise traitlets.TraitError(msg) from e
        else:
            return value  # type: ignore

    def default(self, obj: HasParent, override: None | dict = None) -> T | None:  # type: ignore
        try:
            if not self.load_default and override is None:
                if self.allow_none:
                    return None
                msg = f'Both `load_default` and `allow_none` are False for "{obj.__class__.__qualname__}.{self.name}".'
                raise RuntimeError(msg)  # noqa: TRY301
            kwgs = dict(self.kwgs)
            if issubclass(self.klass, HasParent) and self.set_parent:
                kwgs["parent"] = obj

            # dynamic_kwgs
            if dynamic_kwgs := self.settings.get("dynamic_kwgs"):
                for name, value in dynamic_kwgs.items():
                    if callable(value):
                        kwgs[name] = value(
                            IHPCreate(parent=obj, name=self.name, klass=self.klass, args=self.args, kwgs=kwgs)
                        )
                    elif value == "self":
                        kwgs[name] = obj
                    else:
                        kwgs[name] = utils.getattr_nested(obj, value, hastrait_value=False)

            # children
            if children := self.settings.get("children"):
                if isinstance(children, dict):
                    from menubox.synchronise import ChildrenSetter

                    home = getattr(obj, "home", "_child setter")
                    ChildrenSetter(home=home, parent=obj, name=self.name, items=children["dottednames"])
                else:
                    kwgs["children"] = obj.get_widgets(*children, skip_hidden=False, show=True)

            # Overrides - use via `HasParent.instanceHP_enable_disable`, `Menubox.enable_widget` or set directly with a dict.
            if override:
                kwgs = kwgs | override
            # create
            if create := self.settings.get("create"):
                if isinstance(create, str):
                    create = getattr(obj, create)
                return create(IHPCreate(parent=obj, name=self.name, klass=self.klass, args=self.args, kwgs=kwgs))
            return self.klass(*(self.args), **kwgs)
        except Exception as e:
            obj.on_error(e, f'Instance creation failed for "{utils.fullname(obj)}.{self.name}"', self)
            raise

    def _validate(self, obj: HasParent, value) -> T | None:
        if value is None:
            if self.allow_none:
                return value
            msg = (
                f"None is not allowed for the InstanceHP trait `{obj.__class__.__qualname__}.{self.name}`. "
                f"Use `.configure(allow_none=True)` "
                "to permit it."
            )
            raise RuntimeError(msg)
        if not self.klass:
            msg = f"klass has not been set for the InstanceHP object: {obj.__class__}.{self.name}"
            raise RuntimeError(msg)
        if isinstance(value, self.klass):  # type:ignore[arg-type]
            if obj._cross_validation_lock is False:
                value = self._cross_validate(obj, value)
            return value
        self.error(obj, value)  # noqa: RET503

    def _value_changed(self, owner: HasParent, old: T | None, new: T | None):
        # This is the main handler function for loading and configuration
        # providing consistent/predictable behaviour reducing boilerplate code.

        # on_click
        if (
            isinstance(new, ipw.Button)
            and not isinstance(new, mb.async_run_button.AsyncRunButton)
            and (on_click := self.settings.get("on_click"))
        ):
            if mb.DEBUG_ENABLED:
                if not callable(utils.getattr_nested(owner, on_click) if isinstance(on_click, str) else on_click):
                    msg = f"`{on_click=}` is not callable!"
                    raise TypeError(msg)
                if on_click == "button_clicked" and not asyncio.iscoroutinefunction(owner.button_clicked):
                    msg = f"By convention `{utils.fullname(new)}.button_clicked` must be a coroutine function!"
                    raise TypeError(msg)
            taskname = f"button_clicked[{id(new)}] → {owner.__class__.__qualname__}.{self.name}"

            ref = weakref.ref(owner)
            def _on_click(b: ipw.Button):
                obj: HasParent | None = ref()
                if obj:

                    async def click_callback():
                        callback = utils.getattr_nested(obj, on_click) if isinstance(on_click, str) else on_click
                        try:
                            b.add_class(mb.defaults.CLS_BUTTON_BUSY)
                            result = callback(b)
                            if inspect.isawaitable(result):
                                await result
                        finally:
                            b.remove_class(mb.defaults.CLS_BUTTON_BUSY)

                    mb_async.run_async(click_callback, name=taskname, obj=obj)

            new.on_click(_on_click)

        # set_attrs
        if set_attrs := self.settings.get("set_attrs"):
            for k, v in set_attrs.items():
                val = v
                if isinstance(val, str) and val.startswith("."):
                    val = val[1:]
                    val = owner if val == "self" else utils.getattr_nested(owner, val)
                elif callable(val):
                    config = IHPCreate(parent=owner, name=self.name, klass=self.klass, args=self.args, kwgs=self.kwgs)
                    val = val(config)
                utils.setattr_nested(new, k, val, setattr)

        # dlink
        if dlink := self.settings.get("dlink"):
            dlinks = (dlink,) if isinstance(dlink, dict) else dlink
            target_obj = new
            for dlink in dlinks:
                src_name, src_trait = dlink["source"]
                src_obj = owner if src_name == "self" else utils.getattr_nested(owner, src_name, hastrait_value=False)
                tgt_trait = dlink["target"]
                key = f"{id(owner)} {owner.__class__.__qualname__}.{self.name}.{tgt_trait}"
                if "." in tgt_trait:
                    class_name, tgt_trait = tgt_trait.rsplit(".", maxsplit=1)
                    target_obj = utils.getattr_nested(new, class_name, hastrait_value=False)
                transform = dlink.get("transform")
                if isinstance(transform, str):
                    transform = utils.getattr_nested(owner, transform, hastrait_value=False)
                if transform and not callable(transform):
                    msg = f"Transform must be callable but got {transform:!r}"
                    raise TypeError(msg)
                owner.dlink((src_obj, src_trait), target=None, transform=transform, key=key, connect=False)
                if isinstance(target_obj, traitlets.HasTraits):
                    owner.dlink((src_obj, src_trait), target=(target_obj, tgt_trait), transform=transform, key=key)

        # add_css_class
        if isinstance(new, ipw.DOMWidget) and (css_class_names := self.settings.get("add_css_class")):
            for class_name in utils.iterflatten(css_class_names):
                new.add_class(class_name)

        # on_replace_close
        if old is not None and old is not traitlets.Undefined:
            if isinstance(old, HasParent) and getattr(old, "parent", None) is owner:
                old.parent = None
            if self.settings.get("on_replace_close"):
                mb.utils.close_obj(old)

        # change_new & change_old
        for obj, key in [(old, "change_old"), (new, "change_new")]:
            if obj is not None and (changed := self.settings.get(key)):
                if isinstance(changed, str):
                    changed = getattr(owner, changed)
                changed(IHPChange(name=self.name, parent=owner, obj=obj))

        # value closed
        if (old_observer := self._close_observers.pop(owner, None)) and isinstance(old, HasParent | ipw.Widget):
            with contextlib.suppress(KeyError):
                old.unobserve(**old_observer)

        if isinstance(new, HasParent | ipw.Widget):
            owner_ref = weakref.ref(owner)
            traitname = self.name

            def _observe_closed(change: mb.ChangeType):
                # Check if the change owner has closed, if remove it from parent if appropriate.
                owner_ = owner_ref()
                cname, value = change["name"], change["new"]
                if (
                    owner_
                    and ((cname == "closed" and value) or (cname == "comm" and not value))
                    and owner_._trait_values.get(traitname) is change["owner"]
                ):
                    if self.allow_none and not owner_.closed:
                        owner_.set_trait(traitname, None)
                    else:
                        owner_._reset_trait(traitname)

            names = "closed" if isinstance(new, HasParent) else "comm"
            new.observe(_observe_closed, names)
            self._close_observers[owner] = {"handler": _observe_closed, "names": names}

    # TODO: add overloads if allow_none is True/false
    # TODO: switch to using pluggy hooks.
    def configure(self, **kwgs: Unpack[IHPSettings[T]]) -> Self:
        """Configure how the instance will be handled.

        Configuration changes are merged using a nested replace strategy except as explained below.

        Defaults
        --------
        * load_default: True
        * allow_none: True
        * set_parent: True
        * read_only: True
        * on_replace_close: True
        * on_click: "button_clicked" (Only relevant to buttons)

        Parameters
        ----------
        on_replace_close: Bool
            close/close the previous instance if it is replaced.
            Note: HasParent will not close if its the property `KEEP_ALIVE` is True.
        allow_none :  bool
            Allow the value to be None. Note: If load_default is passed,
        set_parent: Bool [True]
            Set the parent to the owner of the trait (HasParent).
        dynamic_kwgs: dict
            mapping of dynamic kwargs to use during instantiation.
            values can be a mapping of dotted name to an attribute on the parent
            or a callable.
        create: str | callable
            The name of the create function in the parent to generate the default.
            create function is passed bunched settings:
                `Bunched(name:str, klass:type, args:tuple, kwgs:dict)`
        set_attrs: dict[str,any]
            Set the attributes of the instance during validation (after instantiation).
            Accepts dotted name keys. Uses `setattr` as the `default_setter`.
            **Dotted name values**:
                If the value is a string and starts with `.` the value will be replaced
                with the dotted name after the `.`.
            **Callable values**
                If the value is callable, the result of the callable is used. The callable
                is passed the structure `IHPCreate` noting that kwgs is updated in the same
                order as set_attrs.
        dlink: IHPDlinkType | tuple[IHPDlinkType]
            A mapping or tuple of mappings for dlinks to add when creating.
            'source': tuple[obj, str]
            'target: str
            transform: Callable[Any, Any]
                A function to convert the source value to the target value.
        children: ChildrenDict | tuple[str | ipw.Widget | Callable[[], str | ipw.Widget | Callable], ...] <Boxes and Panels only>
            Children are collected from the parent using 'parent.get_widgets'.
            and passed as the keyword argument `children`= (<widget>,...) when creating a new instance.

            Additionally, if mode is 'monitor', the children will be updated as the state
            of the children is changed (including hide/show).

        add_css_class: str | tuple[str, ...] <DOMWidget **ONLY**>
            Class names to add to the instance. Useful for selectors such as context menus.
        on_click: Str | Tuple[str, ...] <Button **ONLY**>
            Dotted name access to the on_click callbacks.
        """
        if "load_default" in kwgs and "allow_none" not in kwgs:
            kwgs["allow_none"] = not kwgs["load_default"]
        if kwgs:
            merge(self.settings, kwgs, strategy=Strategy.REPLACE)  # type:ignore
        return self

    def set_children(
        self,
        *children: str | ipw.Widget | Callable[[], Iterable[ipw.Widget | str]],
        mode: Literal["on default", "monitor"] = "on default",
    ) -> Self:
        """The dotted names of widgets relative parent to use during instantiation.

        Children are collected from the parent using 'parent.get_widgets'.
        and passed as the keyword argument `children`= (<widget>,...) when creating a new instance.

        Additionally, if mode is 'monitor', the children will be updated as the state
        of the children is changed (including hide/show).

        mode: 'on default' | 'monitor'
            'on default': Load the children only when creating from default.
            'monitor' : Same as 'on default' plus monitor children and their visibility and
            reload on demand. The list of children must contain string names of traits
            (dotted paths accepted). When a widget is removed or replaced the children will be updated.
        """
        self.children = children
        self.children_mode = mode
        return self


def instanceHP_wrapper(
    klass: type[T] | str,
    /,
    *,
    defaults: None | dict[str, Any] = None,
    strategy=Strategy.REPLACE,
    tags: None | dict[str, Any] = None,
    **kwargs: Unpack[IHPSettings],
):
    """
    A decorator style function to produce InstanceHP trait for klass.

    Note: the returned instance can also be configured.

    klass:
        The class to base the instance on.
    defaults:
        default values used in the create.
    strategy:
        How defaults are merged with the instance kwargs if a clash occurs with defaults.

    Configure
    ---------
    read_only: boo [ default False ]
        Make the trait read only.
    load_default: bool [default True]
    allow_none : Optional bool
        default : True if load_default is False else False
    tags:
        Default tags to apply (see tags).

    Usage:
    -----

    ```
    Dropdown = instanceHP_wrapper(ipw.Dropdown, defaults={"options": (1, 2, 3)})


    class Widget_Box(MenuBox):
        a = Dropdown(description="a")
        b = Dropdown(description="b").configure(load_default=False)


    wb = Widget_box()
    assert b.a.description == "a"
    wb2 = Widget_box()
    assert wb2.a is not wb
    ```

    """
    defaults_ = merge({}, defaults) if defaults else {}
    tags = dict(tags) if tags else {}

    # TODO : Requires py 3.12+ https://typing.readthedocs.io/en/latest/spec/constructors.html#converting-a-constructor-to-callable
    # Hopefully this will restore documentation to the Constructor.
    def instanceHP_factory(*args, **kwgs) -> InstanceHP[T]:
        """Returns an InstanceHP[klass] trait.

        Use this to add a trait to new subclass of HasParent.

        Specify *args and **kwgs to pass when creating the 'default' (when the trait default is requested).

        Follow the link (ctrl + click): function-> klass to see the class definition and what *args and **kwargs are available.
        """
        kw = merge({}, defaults_, kwgs, strategy=strategy) if defaults_ else kwgs
        instance = InstanceHP(klass, *args, **kw)
        if kwargs:
            instance.configure(**kwargs)
        if tags:
            instance.tag(**tags)
        return instance

    return instanceHP_factory
