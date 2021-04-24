"""
Helper decorators
"""

import logging
import time
from functools import wraps

_logger = logging.getLogger(__name__)


def with_logger(cls):
    """
    Add a `_logger` attribute to a class. The logger name will be the same as
    the class name.

    # Examples
    >>> @with_logger
    ... class Foo:
    ...    pass
    >>> assert Foo._logger.name == "Foo"
    """
    attr_name = "_logger"
    cls_name = cls.__qualname__
    setattr(cls, attr_name, logging.getLogger(cls_name))
    return cls


def _timed_decorator(f, logger=_logger, limit=0.2):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        elapsed = (time.time() - start)
        if elapsed >= limit:
            logger.warning("%s took %s s to finish", f.__name__, str(elapsed))
        return result

    return wrapper


def timed(*args, **kwargs):
    """
    Record the execution time of a function and log a warning if the time
    exceeds a limit.

    # Examples
    >>> import time, mock
    >>> log = mock.Mock()
    >>> @timed(logger=log, limit=0.05)
    ... def foo():
    ...    time.sleep(0.1)
    >>> foo()
    >>> log.warning.assert_called_once()
    """
    if len(args) == 1 and callable(args[0]):
        return _timed_decorator(args[0])
    else:
        return lambda f: _timed_decorator(f, *args, **kwargs)
