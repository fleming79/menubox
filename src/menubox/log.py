import asyncio
import datetime
import functools
import logging
import os
from typing import Any

import ipylab
import ipylab.log
import ipywidgets as ipw
import wrapt

import menubox as mb
from menubox import utils

PID = os.getpid()
_tz = datetime.datetime.now(datetime.UTC).astimezone().tzinfo
if _tz is None:
    msg = "Failed to get Timezone!"
    raise RuntimeError(msg)
TZ = _tz


__all__ = ["START_DEBUG", "on_error_wrapped", "log_exceptions"]


def START_DEBUG(*, to_stdio=False):
    mb.DEBUG_ENABLED = True
    logging.captureWarnings(True)
    import menubox.menubox

    fc = '<font color="grey">'
    menubox.menubox.H_FILL.children = (ipw.HTML(f"{fc}❬"), ipw.HTML(f"{fc}❭"))
    menubox.menubox.V_FILL.children = (ipw.HTML(f"{fc}↑"), ipw.HTML(f"{fc}↓"))
    if to_stdio:
        import sys

        ipylab.app.log_level = ipylab.log.LogLevel.DEBUG
        ipylab.app.shell.log_viewer.buffer_size.value = 0

        def record_to_stdout(record):
            sys.stdout.write(record.output["text"])

        assert ipylab.app.logging_handler  # noqa: S101
        ipylab.app.logging_handler.register_callback(record_to_stdout)
        ipylab.app.log.info("Debugging enabled")


def on_error(error: Exception, msg: str, obj: Any = None):
    """Logs an error message with exception information.

    Args:
        error (Exception): The exception that occurred.
        msg (str): The error message to log.
        obj (Any, optional): An optional object to include in the log message. Defaults to None.
    """
    ipylab.app.log.exception(msg, obj=obj, exc_info=error)


def on_error_wrapped(wrapped, instance, msg, e: Exception):
    """Log an exception locating most appropriate log first.

    raise_exception: bool
        Will raise the exception after logging the error provided the instance/owner is
        not closed.
    """
    if not instance and getattr(wrapped, "__self__", None):
        instance = wrapped.__self__
    if instance and getattr(instance, "closed", False):
        return
    if hasattr(instance, "on_error"):
        instance.on_error(e, msg, obj=wrapped)
    else:
        on_error(e, msg, wrapped)


def log_exceptions(wrapped=None, instance=None, *, loginfo: str = ""):
    callcount = 0
    if wrapped is None:
        return functools.partial(log_exceptions, loginfo=loginfo)
    if not callable(wrapped):
        msg = f"Wrapped function '{wrapped}' is not callable!"
        raise TypeError(msg)
    if asyncio.iscoroutinefunction(wrapped):
        msg = (
            "`log_exceptions` is not allowed for coroutine functions! "
            f"{utils.funcname(wrapped)}\n"
            f"Use run_async({wrapped}, obj=<self ...>) instead."
        )
        raise TypeError(msg)

    @wrapt.decorator
    def _log_exceptions(wrapped, instance, args: tuple, kwargs: dict):
        """Decorator for logging exceptions.

        Will use `instance.log` if it exists, otherwise will use the module logger.
        """
        nonlocal callcount
        callcount += 1
        try:
            return wrapped(*args, **kwargs)
        except Exception as e:
            if callcount > 1:
                raise
            on_error_wrapped(wrapped, instance, loginfo, e)
            raise
        finally:
            callcount -= 1

    return _log_exceptions(wrapped, instance)  # type: ignore


def observe_ipylab_log_level(_):
    def refresh_all_menuboxes():
        for inst in mb.Menubox._instances.values():
            if isinstance(inst, mb.Menubox) and not inst.closed and inst.view:
                inst.mb_refresh()

    if ipylab.app.log_level == ipylab.log.LogLevel.DEBUG:
        START_DEBUG(to_stdio=False)
        refresh_all_menuboxes()
    elif mb.DEBUG_ENABLED:
        mb.DEBUG_ENABLED = False
        refresh_all_menuboxes()


ipylab.app.observe(observe_ipylab_log_level, names="log_level")
