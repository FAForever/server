import logging
import time
from functools import wraps

_logger = logging.getLogger(__name__)


def with_logger(cls):
    attr_name = '_logger'
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
            logger.warn("%s took %s s to finish" % (f.__name__, str(elapsed)))
        return result
    return wrapper


def timed(*args, **kwargs):
    if len(args) == 1 and callable(args[0]):
        return _timed_decorator(args[0])
    else:
        return lambda f: _timed_decorator(f, *args, **kwargs)
