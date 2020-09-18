import contextlib
import weakref
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


# Adapted from https://www.python.org/dev/peps/pep-0487/
class WeakAttribute(Generic[T]):
    """
    Transparently allow an object attribute to reference another object via a
    weak reference.
    """

    def __set_name__(self, _: object, name: str) -> None:
        self.name = name

    def __get__(self, obj: object, objclass: type) -> Optional[T]:
        ref = obj.__dict__.get(self.name)
        if ref:
            return ref()
        return None

    def __set__(self, obj: object, value: T) -> None:
        obj.__dict__[self.name] = weakref.ref(value)

    def __delete__(self, obj: object) -> None:
        with contextlib.suppress(KeyError):
            del obj.__dict__[self.name]
