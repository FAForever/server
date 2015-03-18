import logging
import time
from functools import wraps

_logger = logging.getLogger(__name__)


def with_logger(cls):
    attr_name = '_logger'
    cls_name = cls.__qualname__
    module = cls.__module__
    assert module is not None
    cls_name = module + '.' + cls_name
    setattr(cls, attr_name, logging.getLogger(cls_name))
    return cls


def timed(logger=_logger, limit=0.2):
    def timed_decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = f(*args, **kwargs)
            elapsed = (time.time() - start)
            if elapsed >= limit:
                logger.info("%s took %s s to finish" % (f.__name__, str(elapsed)))
            return result
        return wrapper
    return timed_decorator
