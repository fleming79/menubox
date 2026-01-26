import datetime
import logging
import os
from typing import Any

import ipylab
import ipylab.log
import ipywidgets as ipw

import menubox as mb

PID = os.getpid()
_tz = datetime.datetime.now(datetime.UTC).astimezone().tzinfo
if _tz is None:
    msg = "Failed to get Timezone!"
    raise RuntimeError(msg)
TZ = _tz


__all__ = ["START_DEBUG", "on_error_wrapped"]


def START_DEBUG(*, to_stdio=False):
    mb.DEBUG_ENABLED = True
    logging.captureWarnings(True)
    import menubox.menubox

    fc = '<font color="grey">'
    menubox.menubox.H_FILL.children = (ipw.HTML(f"{fc}❬"), ipw.HTML(f"{fc}❭"))
    menubox.menubox.V_FILL.children = (ipw.HTML(f"{fc}↑"), ipw.HTML(f"{fc}↓"))
    if to_stdio:
        import sys

        app = ipylab.JupyterFrontEnd()
        app.log_level = ipylab.log.LogLevel.DEBUG

        def record_to_stdout(record):
            sys.stdout.write(record.output["text"])

        assert app.logging_handler
        app.logging_handler.register_callback(record_to_stdout)
        app.log.info("Debugging enabled")


def on_error(error: BaseException, msg: str, obj: Any = None) -> None:
    """
    Logs an error message with exception information.

    Args:
        error (Exception): The exception that occurred.
        msg (str): The error message to log.
        obj (Any, optional): An optional object to include in the log message. Defaults to None.
    """
    app = ipylab.JupyterFrontEnd()
    app.log.exception(msg, obj=obj, exc_info=error)


def on_error_wrapped(wrapped, instance, msg, e: Exception) -> None:
    """
    Log an exception locating most appropriate log first.

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
