import contextlib
from typing import Any, Dict, List, Optional

from .typedefs import Handler, HandlerDecorator, Message


class RouteError(Exception):
    """
    Raised when no matching route can be found for a message
    """


class Router():
    """
    Matches messages to handler functions.
    """
    missing = object()

    def __init__(self, dispatch_key: Any = missing):
        self.dispatch_key = dispatch_key
        self.registry = SearchTree()

    def register(self, key: Any = missing, **filters: Any) -> HandlerDecorator:
        def decorator(func: Handler) -> Handler:
            self.register_func(func, key, **filters)
            return func
        return decorator

    def register_func(
        self,
        func: Handler,
        key: Any = missing,
        **filters: Any
    ) -> None:
        """
        Register a handler with a set of filters. Note that the order of
        repeated calls matters as does the order of keyword arguments.

        :param key: Optional convenience for adding a filter using the default
            key: {self.dispatch_key: key}
        """
        if key is not self.missing:
            if self.dispatch_key is self.missing:
                raise RuntimeError("No default `dispatch_key` provided!")
            filters = {self.dispatch_key: key, **filters}
        self.registry.insert(func, filters)

    def dispatch(self, message: Message) -> Handler:
        """
        Get the handler function that matches this message.

        :raises: RouteError if no matching route is found
        """
        with contextlib.suppress(KeyError):
            return self.registry[message]

        raise RouteError("No matching route")


class SearchTreeKeyNode():
    """
    Even-level node for matching against keys.
    """
    def __init__(self) -> None:
        self.handler: Optional[Handler] = None
        self.nodes: List[SearchTreeValueNode] = []

    def __getitem__(self, message: Message) -> Handler:
        """
        Return the matching handler.

        :raises: KeyError if none exists
        """
        for node in self.nodes:
            with contextlib.suppress(KeyError):
                return node[message]

        if self.handler:
            return self.handler

        raise KeyError()

    def get(self, message: Message) -> Optional[Handler]:
        """
        Return the matching handler if it exists, else None.
        """
        with contextlib.suppress(KeyError):
            return self[message]
        return None

    def insert(self, handler: Handler, filters: Dict[Any, Any]) -> None:
        """
        Add a handler to the search tree given a set of filters. Note that the
        order of repeated insert calls matters, as does the iteration order of
        filters.

        # Examples
        ```
        tree.insert("foo_handler", {"first": "foo"})
        tree.insert("bar_handler", {"second": "bar"})

        # Both are present, so first match is returned
        assert tree[{"first": "foo", "second": "bar"}] == "foo_handler"
        ```

        ```
        tree.insert("foo_handler", {"first": "foo", "second": "bar"})

        assert tree.get({"first": "foo"}) == "foo_handler"
        # Second is a subkey of first and does not match on its own
        assert tree.get({"second": "bar"}) is None
        ```
        """
        try:
            key, value = next(iter(filters.items()))
        except StopIteration:
            self.handler = handler
            return

        # Find matching node for `key`
        for value_node in self.nodes:
            if value_node.key == key:
                break
        else:
            value_node = SearchTreeValueNode(key)
            self.nodes.append(value_node)

        # Get the sub-node for `value`
        node = value_node.values.get(value)
        if node is None:
            node = SearchTreeKeyNode()
            value_node.values[value] = node

        # Recurse
        del filters[key]
        node.insert(handler, filters)

    def __repr__(self, level: int = 0) -> str:
        spacing = "    " * level
        nodes = "\n".join(node.__repr__(level + 1) for node in self.nodes)
        return f"{spacing}handler: {self.handler}\n{spacing}nodes:\n{nodes}"


class SearchTreeValueNode():
    """
    Odd-level node for matching against values.
    """
    def __init__(self, key: Any) -> None:
        self.key = key
        self.values: Dict[Any, SearchTreeKeyNode] = {}

    def __getitem__(self, message: Message) -> Handler:
        return self.values[message[self.key]][message]

    def __repr__(self, level: int = 0) -> str:
        spacing = "    " * level
        values = "\n".join(
            f"{spacing}value: {value}\n{node.__repr__(level + 1)}"
            for value, node in self.values.items()
        )
        return f"{spacing}key: {self.key}\n{spacing}values:\n{values}"


SearchTree = SearchTreeKeyNode
