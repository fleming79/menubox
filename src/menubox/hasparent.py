from __future__ import annotations

import asyncio
import contextlib
import weakref
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn, Self, override

import ipywidgets as ipw
import pandas as pd
import toolz
import traitlets
from ipylab.log import IpylabLoggerAdapter
from traitlets import HasTraits

import menubox
import menubox as mb
from menubox import defaults as dv
from menubox import mb_async, utils
from menubox.trait_types import ChangeType, MetaHasParent, NameTuple, ProposalType

__all__ = ["HasParent", "Link", "Dlink"]


if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Generator

    from menubox.instance import InstanceHP


class Link:
    """Link traits from different objects together so they remain in sync.

    Modified copy - traitlets.link
    """

    updating = False

    def __init__(
        self,
        source: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: tuple[Callable[[Any], Any], Callable[[Any], Any]] | None = None,
        *,
        obj: HasParent,
    ):
        traitlets.traitlets._validate_link(source, target)
        self.source, self.target = source, target
        if obj:
            if not isinstance(obj, HasParent):
                msg = f"obj must be an instance of HasParent not {type(obj)}"
                raise TypeError(msg)
            if obj.closed:
                msg = f"{obj=} is closed!"
                raise RuntimeError(msg)
        self.obj = obj
        self._transform, self._transform_inv = transform or (self._pass_through,) * 2
        self.link()

    def __repr__(self) -> str:
        return (
            f"Link source={self.source[0].__class__.__qualname__}.{self.source[1]} "
            f" target={self.target[0].__class__.__qualname__}.{self.target[1]}"
        )

    @contextlib.contextmanager
    def _busy_updating(self):
        self.updating = True
        try:
            yield
        finally:
            self.updating = False

    def _pass_through(self, x):
        return x

    def _obj_closed_observe(self, _: ChangeType):
        self.unlink()

    def link(self):
        setattr(
            self.target[0],
            self.target[1],
            self._transform(getattr(self.source[0], self.source[1])),
        )
        self.source[0].observe(self._update_target, names=self.source[1])
        self.target[0].observe(self._update_source, names=self.target[1])
        if self.obj:
            self.obj.observe(self._obj_closed_observe, names="closed")

    def _update_target(self, change: ChangeType):
        if self.updating or not self._transform:
            return
        if self.obj and self.obj.closed:
            self.unlink()
            return
        with self._busy_updating():
            try:
                setattr(self.target[0], self.target[1], self._transform(change["new"]))
                value = getattr(self.source[0], self.source[1])
                if not self.obj.check_equality(value, change["new"]):
                    msg = f"Broken link {self}: the source value changed while updating the target."
                    raise traitlets.TraitError(msg)  # noqa: TRY301
            except traitlets.TraitError as e:
                msg = (
                    f"Link {utils.fullname(self.source[0])}.{self.source[1]}->"
                    f"{utils.fullname(self.source[0])}.{self.target[1]}"
                )
                self.obj.on_error(e, msg, self)
                if mb.DEBUG_ENABLED:
                    raise

    def _update_source(self, change: ChangeType):
        if self.updating or not self._transform:
            return
        if self.obj and self.obj.closed:
            self.unlink()
            return
        with self._busy_updating():
            setattr(self.source[0], self.source[1], self._transform_inv(change["new"]))
            value = getattr(self.target[0], self.target[1])
            if not self.obj.check_equality(value, change["new"]):
                msg = f"Broken link {self}: the target value changed while updating the source."
                raise traitlets.TraitError(msg)

    def unlink(self):
        if self.obj:
            with contextlib.suppress(Exception):
                self.obj.unobserve(self._obj_closed_observe, names="closed")
        with contextlib.suppress(Exception):
            self.source[0].unobserve(self._update_target, names=self.source[1])
        with contextlib.suppress(Exception):
            self.target[0].unobserve(self._update_source, names=self.target[1])


class Dlink:
    """Link traits from different objects together so they remain in sync.

    Modified copy - traitlets.directional_link
    """

    updating = False

    def __init__(
        self,
        source: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: Callable[[Any], Any] | None = None,
        *,
        obj: HasParent,
    ):
        traitlets.traitlets._validate_link(source, target)
        self._transform = transform or self._pass_through
        self.source, self.target = source, target
        if obj:
            if not isinstance(obj, HasParent):
                msg = f"obj must be an instance of HasParent not {type(obj)}"
                raise TypeError(msg)
            if obj.closed:
                msg = f"{obj=} is closed!"
                raise RuntimeError(msg)
        self.obj = obj
        self.link()

    def __repr__(self) -> str:
        return (
            f"Dlink source={self.source[0].__class__.__qualname__}.{self.source[1]} "
            f" target={self.target[0].__class__.__qualname__}.{self.target[1]}"
        )

    @contextlib.contextmanager
    def _busy_updating(self):
        self.updating = True
        try:
            yield
        finally:
            self.updating = False

    def _pass_through(self, x):
        return x

    def _obj_closed_observe(self, _: ChangeType):
        self.unlink()

    def link(self):
        try:
            setattr(
                self.target[0],
                self.target[1],
                self._transform(getattr(self.source[0], self.source[1])),
            )
        finally:
            self.source[0].observe(self._update, names=self.source[1])
        if self.obj:
            self.obj.observe(self._obj_closed_observe, names="closed")

    def _update(self, change):
        if self.updating or not self._transform:
            return
        if self.obj and self.obj.closed:
            self.unlink()
            return
        with self._busy_updating():
            try:
                setattr(self.target[0], self.target[1], self._transform(change["new"]))
            except Exception as e:
                self.obj.on_error(e, "dlink", self)
                if mb.DEBUG_ENABLED:
                    raise

    def unlink(self):
        if self.obj:
            with contextlib.suppress(Exception):
                self.obj.unobserve(self._obj_closed_observe, names="closed")
        with contextlib.suppress(Exception):
            self.source[0].unobserve(self._update, names=self.source[1])


class Parent(traitlets.TraitType):
    """"""

    allow_none = True
    default_value = None

    def _validate(self, obj: HasParent, value: HasParent | None | Any) -> HasParent | None:
        if value is None:
            return None
        if isinstance(value, HasParent):
            p = value
            while isinstance(p, HasParent):
                if p is obj:
                    msg = f"Unable to set parent of {value!r} because {obj!r} is already a parent or ancestor!"
                    raise RuntimeError(msg)
                p = p.parent
            return value
        msg = "Parent must be either an instance of HasParent or None"
        raise TypeError(msg)


class HasParent(HasTraits, metaclass=MetaHasParent):
    """A base class for objects that have a parent-child relationship and enhanced trait management.

    Key Features:
    - Singleton Instance Management:  Optionally creates singleton instances based on specified attributes (SINGLETON_BY).
    - Nested Attribute Loading:  Recursively loads attributes from dictionaries into the object and its children.
    - Trait Linking:  Provides methods for linking and unlinking traits between objects (link, dlink).
    - Error Handling:  Includes a robust error handling mechanism with logging (on_error).
    - Asynchronous Task Management:  Supports asynchronous initialization and task management.
    - Widget Retrieval:  Facilitates the retrieval of widgets associated with the object.
    - Automatic parent closed handling.
    Key Attributes:
    - parent: A Parent trait representing the parent object.
    - name: A Unicode trait for the object's name.
    - log: An IpylabLoggerAdapter instance for logging.
    - closed: A boolean trait indicating whether the object is closed.
    Usage:
    Inherit from this class to create objects that require parent-child relationships,
    singleton instances, trait linking, and enhanced attribute management.
    """

    RENAMEABLE = True
    KEEP_ALIVE = False
    SINGLETON_BY: ClassVar[tuple[str, ...] | None] = None
    _singleton_instances: ClassVar[weakref.WeakValueDictionary[tuple, Any]] = weakref.WeakValueDictionary()
    _singleton_instances_key: tuple | None = None
    _singleton_key_template: ClassVar[str] = ""
    _InstanceHP: ClassVar[dict[str, InstanceHP[HasParent]]] = {}
    _HasParent_init_complete = False
    _prohibited_parent_links: ClassVar[set[str]] = set()
    _hp_reg_parent_link = traitlets.Set()
    _hp_reg_parent_dlink = traitlets.Set()
    _hp_reg_links = traitlets.Set()
    _hasparent_all_links: traitlets.Dict[str, Link | Dlink] = traitlets.Dict(
        default_value={},
        value_trait=traitlets.Union([traitlets.Instance(Link), traitlets.Instance(Dlink)]),
        key_trait=traitlets.Unicode(),
        read_only=True,
    )
    closed = traitlets.Bool()
    parent_dlink = NameTuple()
    parent_link = NameTuple()
    name: traitlets.Unicode[str, str | bytes] = traitlets.Unicode()
    log = traitlets.Instance(IpylabLoggerAdapter)
    parent = Parent()
    tasks = traitlets.Set(traitlets.Instance(asyncio.Task), read_only=True)
    _init_task: traitlets.Instance[asyncio.Task[None] | None] = traitlets.Instance(asyncio.Task, allow_none=True)  # type: ignore
    init_async: ClassVar[None | Coroutine] = None

    def __new__(cls, *args, **kwargs):
        def _make_key():
            key = [cls.__qualname__]
            if not isinstance(cls.SINGLETON_BY, tuple):
                raise TypeError
            for n in cls.SINGLETON_BY:
                if n == "cls":
                    val = n
                else:
                    val = kwargs.get(n) or getattr(cls, n, None)
                    if val and isinstance(val, traitlets.TraitType):
                        val = val.default_value
                    if not val or val is traitlets.Undefined:
                        msg = f"SINGLETON_BY key '{n}' value not provided or invalid for {cls=}."
                        raise ValueError(msg)
                key.append(val)
            return tuple(key)

        key = _make_key() if cls.SINGLETON_BY else None
        if key and key in cls._singleton_instances:
            return cls._singleton_instances[key]
        # class definitions per
        inst = super().__new__(cls, *args, **kwargs)
        if key:
            if not isinstance(cls.SINGLETON_BY, tuple):
                raise TypeError
            if "name" in cls.SINGLETON_BY:
                inst.name = key[cls.SINGLETON_BY.index("name") + 1]
            cls._singleton_instances[key] = inst
            inst._singleton_instances_key = key
        return inst

    def __init__(self, *, parent: HasParent | None = None, **kwargs):
        """Initialize the HasParent class.

        Args:
            parent: The parent object.
            **kwargs: Keyword arguments to pass to the super class.
        """
        if self._HasParent_init_complete:
            return
        values = {}
        for name in tuple(kwargs):
            if name in self._InstanceHP:
                values[name] = kwargs.pop(name)
        super().__init__(**kwargs)
        self.parent = parent
        self._HasParent_init_complete = True
        for name, v in values.items():
            self.instanceHP_enable_disable(name, v)
        if self.init_async:
            assert asyncio.iscoroutinefunction(self.init_async)  # noqa: S101
            mb_async.run_async(self.init_async, tasktype=mb_async.TaskType.init, obj=self, handle="_init_task")  # type: ignore
            self.init_async = None  # type: ignore # This function is only intended to be called once here.

    def __del__(self):
        self.close(force=True)

    def __init_subclass__(cls, **kwargs) -> None:
        if cls.SINGLETON_BY:
            assert isinstance(cls.SINGLETON_BY, tuple)  # noqa: S101
            if cls.SINGLETON_BY and "name" in cls.SINGLETON_BY:
                cls.RENAMEABLE = False
        cls._cls_update_InstanceHP_register()
        super().__init_subclass__(**kwargs)

    @classmethod
    def _cls_update_InstanceHP_register(cls: type[HasParent]) -> None:
        tn_ = dict(cls._InstanceHP)
        for c in cls.mro():
            if c is __class__:
                break
            if issubclass(c, HasParent) and c._InstanceHP:
                # Need to copy other InstanceHP mappings in case of multiple subclassing
                for name in c._InstanceHP:
                    if name and name not in tn_:
                        tn_[name] = c._InstanceHP[name]
        cls._InstanceHP = tn_

    @classmethod
    def validate_name(cls, name: str) -> str:
        return name

    @traitlets.validate("name")
    def _hp_validate_name(self, proposal: ProposalType) -> str:
        if not self.RENAMEABLE and self.trait_has_value("name") and self.name:
            return self.name
        return self.validate_name(proposal["value"]).strip()

    @traitlets.validate("parent_link", "parent_dlink")
    def _parent_link_dlink_validate(self, proposal: ProposalType):
        if prohibited := self._prohibited_parent_links.intersection(proposal["value"]):
            msg = f"Prohibited links detected: {prohibited}"
            raise NameError(msg)
        links = []
        for link in toolz.unique(proposal["value"]):
            if not self.has_trait(link):
                msg = f"{utils.fullname(self)} does not have the trait '{link}'"
                raise AttributeError(msg)
            links.append(link)
        return tuple(links)

    @traitlets.default("log")
    def _default_log(self):
        return IpylabLoggerAdapter(utils.fullname(self), owner=self)

    @traitlets.observe("parent", "parent_link", "parent_dlink")
    def _observe_parent(self, change: ChangeType):
        if change["name"] == "parent":
            if isinstance(change["old"], HasParent):
                with contextlib.suppress(Exception):
                    change["old"].unobserve(self._hp_parent_closed, "closed")
            if isinstance(change["new"], HasParent):
                change["new"].observe(self._hp_parent_closed, "closed")
        p_link = set()
        p_dlink = set()
        if self.parent:
            for n in self.parent_link:
                if self.parent.has_trait(n):
                    p_link.add((self.parent, n))
            for n in self.parent_dlink:
                if self.parent.has_trait(n):
                    p_dlink.add((self.parent, n))
        self._hp_reg_parent_link = p_link
        self._hp_reg_parent_dlink = p_dlink

    @traitlets.observe("_hp_reg_parent_link", "_hp_reg_parent_dlink")
    def _observe__hp_reg_parent_link(self, change: ChangeType):
        # Update links
        old = change["old"] if isinstance(change["old"], set) else set()
        mname = change["name"].rsplit("_", maxsplit=1)[1]
        method = self.link if mname == "link" else self.dlink
        # remove old links
        for _, name in set(old).difference(change["new"]):
            method((), (), key=f"{mname}_{name}", connect=False)  # type: ignore
        # add new links
        for parent, name in change["new"].difference(old):
            v = getattr(self, name)
            target = (v, "value") if isinstance(v, ipw.ValueWidget) and not isinstance(v, HasParent) else (self, name)
            val = getattr(parent, name)
            if isinstance(val, ipw.ValueWidget) and not isinstance(val, HasParent):
                source = val, "value"
            else:
                source = parent, name
            method(source, target, key=f"{mname}_{name}")

    def setter(self, obj, name: str, value):
        """setattr with pre-processing.

        Called during load_nested_attrs .

        Notably special handling is provisioned for ValueTraits subclasses where the
        object can be specified.
        """
        from menubox import valuetraits as vt

        if isinstance(obj, ipw.Combobox) and name == "value":
            if value is None:
                value = ""
            value = str(value)
        if (
            isinstance(obj, ipw.widget_selection._Selection) and name == "value" and isinstance(value, str)
        ) and value == "":
            value = None
        val = getattr(obj, name, dv.NO_VALUE)
        if val is not dv.NO_VALUE:
            if isinstance(val, vt.ValueTraits) and not isinstance(value, vt.ValueTraits):
                obj = val
                name = "value"
                if callable(obj.setter):
                    utils.setattr_nested(obj, name, value, default_setter=obj.setter)
                    return
            elif (
                name != "value"
                and isinstance(val, HasTraits)
                and not isinstance(value, HasTraits)
                and val.has_trait("value")
            ):
                # Support for loading the value back into a HasTraits instance (Widget)
                obj = val
                name = "value"
        if isinstance(obj, HasTraits) and obj.has_trait(name):
            obj.set_trait(name, value)
        else:
            setattr(obj, name, value)

    def load_nested_attrs(
        self,
        obj,
        values: dict | Callable[[], dict],
        raise_errors: bool = True,  # noqa: FBT001
        default_setter: Callable[[Any, str, Any], None] = setattr,
    ) -> dict[str, Any]:
        """Recursively load a dict of nested attributes into obj.

        values: dict

        raise_errors:
            Will raise setting errors if they occur.
            If False - a warning will be issued.
        default_setter:
            override the setter. default is mb.utils.setter
        Will return a dict of successfully set values.
        """
        while callable(values):
            values = values()
        if not isinstance(values, dict):
            if raise_errors:
                msg = f"values is not a dict {type(values)}="
                raise AttributeError(msg)
            return {}
        kwn = {}
        for attr, value in values.items():
            try:
                utils.setattr_nested(obj, attr, value, default_setter=default_setter)
                kwn[attr] = value
            except Exception as e:
                self.on_error(
                    error=e,
                    msg=f"Could not set nested attribute:  {utils.fullname(obj)}.{attr} = {utils.limited_string(value)} --> {e}",
                    obj=obj,
                )
                if raise_errors:
                    raise
        return kwn

    def check_equality(self, a, b) -> bool:
        """Check objects are equal. Special handling for DataFrame."""
        if isinstance(a, pd.DataFrame):
            return a.equals(b)
        return a == b

    def get_log_name(self):
        "A representation for logging"
        return utils.limited_string(self, 40)

    @override
    def add_traits(self, **_: Any) -> NoReturn:
        """-- DO NOT USE --

        The traitlets version of this function overwrites the class meaning
        that isininstance & issubclass fail causing unexpected behaviour.
        """

        msg = "Make a subclass instead."
        raise NotImplementedError(msg)

    def on_error(self, error: Exception, msg: str, obj: Any = None):
        """Logs an error message with exception information.

        Note: When overloading, do not raise the error, it should by the callee after this function returns.
            It may be useful to add a note to the exception if applicable.

        Args:
            error (Exception): The exception that occurred.
            msg (str): The error message to log.
            obj (Any, optional): An object associated with the error. Defaults to None.
        """
        self.log.exception(msg, obj=obj, exc_info=error)

    def _hp_parent_closed(self, _: ChangeType):
        try:
            self.close()
        except Exception as e:
            self.on_error(e, "close failed")
            if mb.DEBUG_ENABLED:
                raise

    def instanceHP_enable_disable(self, name: str, enable: bool | dict):
        """Enables or disables an InstanceHP trait.
        Args:
            name: The name of the instance HP to enable or disable.
            enable:
            If True or a dict, the instance HP is enabled. If a dict, it
            becomes the value of the instance HP. If False or None, the
            instance HP is disabled (set to None).
        Raises:
            KeyError: If the given name is not a valid instance HP.
        """

        if name not in self._InstanceHP:
            msg = f"{name=} not in {list(self._InstanceHP)}"
            raise KeyError(msg)
        if enable in [False, None]:
            self.set_trait(name, None)
        elif self._trait_values.get(name) is None:
            self.set_trait(name, {} if enable is True else enable)

    def _reset_trait(self, name: str):
        """Reset the trait to an unloaded stated."""
        if name in self._trait_values:
            self.log.debug("InstanceHP resetting trait %s", name)
            if self._InstanceHP[name].allow_none:
                self.set_trait(name, None)
            self._trait_values.pop(name)

    def close(self, force=False):
        """Closes the object, disconnecting it from its parent and cleaning up resources.

        Designed to be compatible with `Widget.close`.

        Args:
            force (bool, optional): If True, forces the object to close even if KEEP_ALIVE is set. Defaults to False.
        """
        if self.closed or (self.KEEP_ALIVE and not force):
            return
        self.closed = True
        close = getattr(super(), "close", None)
        if callable(close):
            close()
        self.log.debug("Closed")
        if self._singleton_instances_key:
            self._singleton_instances.pop(self._singleton_instances_key, None)
        self.set_trait("parent", None)
        if self.trait_has_value("_hasparent_all_links"):
            for link in self._hasparent_all_links.values():
                link.unlink()
            self._hasparent_all_links.clear()
        # Reset the object.
        for n in ["_trait_notifiers", "_trait_values", "_trait_validators"]:
            d = getattr(self, n, None)
            if isinstance(d, dict):
                d.clear()
        self.closed = True  # Need to restore this trait to false.

    def fstr(self, string: str, raise_errors=False, parameters: dict | None = None) -> str:
        """Formats string using fstr type notation.

        `self`, 'mb', `record` and `df` are available in the namespace.
        """
        if not string:
            return ""
        g = globals() | {"self": self, "mb": menubox} | (parameters or {})
        try:
            return utils.fstr(string, raise_errors=raise_errors, **g)
        except Exception:
            if raise_errors or mb.DEBUG_ENABLED:
                raise
            self.log.exception(f"Unable to process fstr for '{string=}' class={utils.fullname(self)}")
            return string

    def link(
        self,
        src: tuple[HasTraits, str],
        target: tuple[HasTraits, str],
        transform: tuple[
            Callable[[Any], Any],
            Callable[[Any], Any],
        ]
        | None = None,
        connect=True,
        key="",
    ):
        """Does link and keeps a reference link until closed.

        Designed to link the target to one source at a time.
        note: there is no need to use connect=False if simply updating the link for a
        new source.
        """
        k = key or f"{id(target[0])}_link_{target[1]}"
        if k in self._hasparent_all_links:
            self._hasparent_all_links.pop(k).unlink()
        if connect:
            link = Link(src, target, transform=transform, obj=self)
            self._hasparent_all_links[k] = link

    def dlink(
        self,
        src: tuple[HasTraits, str],
        target: tuple[HasTraits, str] | None,
        transform: Callable[[Any], Any] | None = None,
        connect=True,
        key="",
    ):
        """Does dlink and and keeps a reference link until closed.

        Designed to dlink the target to one source at a time.
        note: there is no need to use connect=False if simply updating the link for a
        new source.
        """
        if not key:
            if not target:
                msg = ""
                raise ValueError(msg)
            key = f"{id(target[0])}_dlink_{target[1]}"
        if key in self._hasparent_all_links:
            self._hasparent_all_links.pop(key).unlink()
        if connect:
            if not target:
                msg = "A target is required when connecting!"
                raise ValueError(msg)
            link = Dlink(src, target, transform=transform, obj=self)
            self._hasparent_all_links[key] = link

    async def button_clicked(self, b: ipw.Button):
        """Handles button click events.

        When overriding this method, ensure to pass on click events by calling:

        ``` python
        await super().button_clicked(b)
        ```
        Args:
            b (ipw.Button): The button that was clicked.
        """

        button_clicked = getattr(super(), "button_clicked", None)
        if button_clicked:
            await button_clicked(b)

    async def wait_update_tasks(self, timeout=None) -> Self:
        await self.wait_tasks(
            mb_async.TaskType.update, mb_async.TaskType.init, mb_async.TaskType.click, timeout=timeout
        )
        return self

    async def wait_init_tasks(self, timeout=None) -> Self:
        "Will await init tasks once"
        if self._init_task:
            await self.wait_tasks(mb_async.TaskType.init, timeout=timeout)
        return self

    async def wait_tasks(self, *tasktypes: mb_async.TaskType, timeout=None) -> Self:
        """Waits for tasks to complete belonging to this object, with an optional timeout.

        Tasks are added to this objects `tasks` set automatically when using `mb_async.run_async`.
        The tasktype is also specified when creating the task.

        Args:
            *tasktypes:  The TaskType wait for.
            If none are provided, all non-continuous tasks are waited for.
            timeout: Optional timeout in seconds. If exceeded, the waiting tasks are cancelled.
        Returns:
            Self: Returns the instance of the class.
        Raises:
            TypeError: If any of the provided tasktypes are not instances of TaskType.
        """

        if self.tasks:
            tasktypes_ = []
            for tt in tasktypes or mb_async.TaskType:
                if not isinstance(tt, mb_async.TaskType):
                    raise TypeError(str(tt))
                if tt is not mb_async.TaskType.continuous:
                    tasktypes_.append(tt)
            current_task = asyncio.current_task()
            if tasks := [
                t
                for t in self.tasks
                if t is not current_task and mb_async.background_tasks.get(t, mb_async.TaskType.general) in tasktypes_
            ]:
                async with asyncio.timeout(timeout):
                    await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
        return self

    def get_widgets(
        self: HasParent, *items: utils.GetWidgetsInputType, skip_disabled=False, skip_hidden=True, show=True
    ) -> Generator[ipw.Widget, None, None]:
        """Get widgets from a variety of input types ignoring invalid of closed items..

        Args:
            *items: A variable number of arguments, each of which can be:
            - A single widget.
            - A list of widgets.
            - A dictionary where values are widgets.
            - A callable that returns widgets or list of widgets.
            skip_disabled: If True, disabled widgets are skipped.
            skip_hidden: If True, hidden widgets are skipped.
            show: If True, the widget (Menubox) is displayed.

        Yields:
            Each widget found in the input items.
        """
        yield from utils.get_widgets(
            *items, skip_disabled=skip_disabled, skip_hidden=skip_hidden, show=show, parent=self
        )

    def get(self, name: str, default=None):
        """Same as dict.get method."""
        return getattr(self, name, default)
