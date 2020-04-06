"""
Some helpers for cleaning up code on iterables.
"""
from typing import Generator, Iterable, TypeVar

T = TypeVar("T")


def flatten(l: Iterable[Iterable[T]]) -> Generator[T, None, None]:
    """
    Turn a list of lists into a single list.
    # Example
    ```
    assert list(flatten([1], [1, 2], [1, 2, 3])) == [1, 1, 2, 1, 2, 3]
    ```
    """
    return (item for sublist in l for item in sublist)
