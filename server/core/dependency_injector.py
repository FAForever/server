import inspect
from collections import ChainMap, defaultdict
from typing import Dict, List

DependencyGraph = Dict[str, List[str]]


class DependencyInjector(object):
    """
    Does dependency injection.

    Dependencies are resolved by parameter name. So if a class has init method
    ```
    def __init__(self, hello, world):
        pass
    ```
    the injector will look for two dependencies, called `hello` and `world`.
    These could either be an object registered with `add_injectables`, or an
    instance of another class passed to `build_classes`.

    Injected arguments are only ever constructed once. So if two classes both
    depend on an object called `hello`, then they will both receive the same
    instance of the object called `hello` (whether that is an injectable, or
    another class in the class list).

    # Example
    ```
    class SomeClass(object):
        def __init__(self, external):
            self.external = external

    class SomeOtherClass(object):
        def __init__(self, some_class):
            self.some_class = some_class

    injector = DependencyInjector()
    injector.add_injectables(external=object())
    classes = injector.build_classes({
        "some_class": SomeClass,
        "other": SomeOtherClass
    })

    assert isinstance(classes["some_class"], SomeClass)
    assert isinstance(classes["other"], SomeOtherClass)
    assert classes["other"].some_class is classes["some_class"]
    ```

    """

    def __init__(self) -> None:
        # Objects which are available to the constructors of injected objects
        self.injectables: Dict[str, object] = {}

    def add_injectables(
        self, injectables: Dict[str, object] = {}, **kwargs: object
    ) -> None:
        """
        Register additional objects that can be requested by injected classes.
        """
        self.injectables.update(injectables)
        self.injectables.update(kwargs)

    def build_classes(
        self, classes: Dict[str, type] = {}, **kwargs: type
    ) -> Dict[str, object]:
        """
        Resolve dependencies by name and instantiate each class.
        """
        # kwargs is temporary so we won't be messing with the caller's data
        kwargs.update(classes)
        classes = kwargs

        dep = self._make_dependency_graph(classes)
        # Can get away with a shallow copy because dep values are not modified
        # in-place.
        param_map = dep.copy()

        instances = self._build_classes_from_dependencies(
            dep, classes, param_map
        )
        self.add_injectables(**instances)
        return instances

    def _make_dependency_graph(self, classes: Dict[str, type]) -> DependencyGraph:
        """
        Build dependency graph
        """
        graph: DependencyGraph = defaultdict(list)
        for name in self.injectables:
            graph[name] = []

        for obj_name, klass in classes.items():
            signature = inspect.signature(klass.__init__)
            # Strip off the `self` parameter
            params = list(signature.parameters.values())[1:]
            graph[obj_name] = [param.name for param in params]

        return graph

    def _build_classes_from_dependencies(
        self,
        dep: DependencyGraph,
        classes: Dict[str, type],
        param_map: Dict[str, List[str]]
    ) -> Dict[str, object]:
        """
        Tries to build all classes in the dependency graph. Raises RuntimeError
        if some dependencies are not available or there was a cyclic dependency.
        """
        instances: Dict[str, object] = {}
        resolved = ChainMap(instances, self.injectables)

        while True:
            if not dep:
                return instances

            # Find all services with no dependencies (leaves of our graph)
            leaves = [
                name for name, dependencies in dep.items() if not dependencies
            ]
            if not leaves:
                # Find which dependencies could not be resolved
                missing = {
                    d for dependencies in dep.values()
                    for d in dependencies if d not in dep
                }
                if missing:
                    raise RuntimeError(
                        f"Some dependencies could not be resolved: {missing}"
                    )
                else:
                    cycle = tuple(dep.keys())
                    raise RuntimeError(
                        f"Could not resolve cyclic dependency: {cycle}"
                    )

            # Build all objects with no dependencies
            for obj_name in leaves:
                if obj_name not in resolved:
                    klass = classes[obj_name]
                    param_names = param_map[obj_name]

                    # Build instances using the objects we've resolved so far
                    instances[obj_name] = klass(**{
                        param: resolved[param]
                        for param in param_names
                    })
                else:
                    instances[obj_name] = resolved[obj_name]

                del dep[obj_name]

            # Remove leaves from the dependency graph
            for name, dependencies in dep.items():
                dep[name] = [d for d in dependencies if d not in leaves]
