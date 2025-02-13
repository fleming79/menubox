from __future__ import annotations

import ast
import contextlib
import functools
import io
import pathlib
from typing import TYPE_CHECKING, Any, overload

import numpy as np
import orjson
import pandas as pd
import ruamel.yaml.scalarstring
import traitlets

from menubox import utils
from menubox.defaults import NO_VALUE, is_no_value

if TYPE_CHECKING:
    from fsspec import AbstractFileSystem

    from menubox.defaults import NO_VALUE_TYPE

# ruff: noqa: UP038

__all__ = [
    "json_default_converter",
    "to_dict",
    "to_list",
    "to_json_dict",
    "to_json_list",
    "to_yaml_dict",
    "to_yaml_list",
    "load_yaml",
    "to_yaml",
    "deep_copy",
]


def json_default_converter(obj, unknown_to_str=False):
    """Converters for value_traits and numpy arrays. Also checks for _to_dict and
    name.

    usage:

    json.dumps(my_dict, default=json_default_converter)
    """
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.to_pydatetime()
    if isinstance(obj, pd.DataFrame):
        df = obj.copy()
        df.columns = df.columns.astype(str)
        df.index = df.index.astype(str)
        return df.to_dict()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, traitlets.HasTraits) and hasattr(obj, "value"):
        return obj.value  # type: ignore
    if pd.isna(obj):  # type: ignore
        return None
    if isinstance(obj, pathlib.Path):
        return obj.as_posix()
    if hasattr(obj, "_repr_keys"):
        return {k: getattr(obj, k) for k in obj._repr_keys()}  # type: ignore
    if callable(obj):
        while callable(obj):
            obj = obj()
        return obj
    if unknown_to_str:
        return str(obj)
    msg = f"Conversion of {utils.fullname(obj)} to json is unknown"
    raise TypeError(msg)


def to_dict(x) -> dict:
    """Attempt to convert x to a dict.

    Will return a new (possibly empty) dict
    """
    while callable(x):
        x = x()
    if isinstance(x, dict):
        return dict(x)
    if isinstance(x, str):
        if not x:
            return {}
        try:
            val = load_yaml(x)
        except Exception:
            val = ast.literal_eval(x)
        if isinstance(val, dict):
            return val
    if is_no_value(x, include_na=True):
        return {}
    return dict(x)  # type: ignore


def to_list(x) -> list:
    """Attempt to convert x to a list.

    Will always return a new (possibly empty) list.
    """
    while callable(x):
        x = x()
    if isinstance(x, (list, tuple, dict)):
        return list(x)
    if is_no_value(x, include_na=True):
        return []
    if isinstance(x, str):
        val = NO_VALUE
        try:
            val = load_yaml(x)
        except Exception:
            with contextlib.suppress(Exception):
                val = ast.literal_eval(x)
        if is_no_value(val):
            return []
        if isinstance(val, (list, tuple, dict)):
            return list(val)
        return [x]
    try:
        return list(x)  # type: ignore
    except Exception:
        return [x]


def to_json_dict(value, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_INDENT_2) -> str:
    """Validate proposal text with json formatting, converting to a dict first where possible."""
    data = to_dict(value)
    return orjson.dumps(data, default=json_default_converter, option=option).decode()


def to_json_list(value, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_INDENT_2) -> str:
    """Validate proposal text with json formatting, converting to a list first where possible."""
    data = to_list(value)
    return orjson.dumps(data, default=json_default_converter, option=option).decode()


def to_yaml_dict(value) -> str | NO_VALUE_TYPE:
    """Validate proposal text with yaml formatting, converting to a dict first where possible."""
    return to_yaml(to_dict(value), walkstring=True)


def to_yaml_list(value) -> str | NO_VALUE_TYPE:
    """Transform value to yaml, converting to a list first where possible."""
    return to_yaml(to_list(value), walkstring=True)


def load_yaml(data: str | Any) -> dict | str | list | None:
    _yaml_reader = ruamel.yaml.YAML(typ="safe")
    if isinstance(data, str):
        return _yaml_reader.load(io.BytesIO(data.encode()))
    return _yaml_reader.load(data)


if TYPE_CHECKING:

    @overload
    def to_yaml(data) -> str: ...
    @overload
    def to_yaml(data, walkstring: bool) -> str: ...  # noqa: FBT001
    @overload
    def to_yaml(data, walkstring: bool, fs: None, path: None) -> str: ...  # noqa: FBT001
    @overload
    def to_yaml(data, walkstring: bool, fs: AbstractFileSystem, path: str) -> None: ...  # noqa: FBT001


def to_yaml(data: Any, walkstring=True, fs: AbstractFileSystem | None = None, path: str | None = None) -> str | None:
    """Convert data to yaml string or write to path.

    walkstring: Will check for multiline strings and pass them.
    fs: fsspec.AbstractFileSystem
    path: path to write to using fs.

    returns a yaml string if fs and path not provided.
    """
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.width = 4096

    while callable(data):
        data = data()
    data = load_yaml(data) if isinstance(data, str) else deep_copy(data)
    if walkstring:
        ruamel.yaml.scalarstring.walk_tree(data)
    if fs or path:
        if not (fs and path):
            msg = "Both `fs` and `path` are required if one is provided!"
            raise ValueError(msg)
        with fs.open(path, "wb") as f:
            yaml.dump(data, f)
            return None
    else:
        with io.BytesIO() as s:
            yaml.dump(data, s)
            return s.getvalue()[:-1].decode("utf-8")


def deep_copy[T](obj: T, unknown_to_str=False) -> T:
    """Deep copy by orjson roundtrip."""
    _default_convert = functools.partial(
        getattr(obj, "json_default_converter", json_default_converter), unknown_to_str=unknown_to_str
    )
    return orjson.loads(orjson.dumps(obj, default=_default_convert, option=orjson.OPT_SERIALIZE_NUMPY))
