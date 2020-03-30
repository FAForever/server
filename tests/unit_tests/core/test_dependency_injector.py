import pytest
from server.core import DependencyInjector


@pytest.fixture
def injector():
    return DependencyInjector()


def test_dependency_injector_builds_classes(injector):
    class A:
        def __init__(self) -> None:
            pass

    class B:
        def __init__(self) -> None:
            pass

    classes = injector.build_classes({"a": A, "b": B})

    assert isinstance(classes["a"], A)
    assert isinstance(classes["b"], B)


def test_dependency_injector_only_builds_once(injector):
    class A:
        def __init__(self) -> None:
            pass

    classes = injector.build_classes({"a": A})
    classes2 = injector.build_classes({"a": A})

    assert classes["a"] is classes2["a"]


def test_dependency_injector_resolves_dependencies(injector):
    class A:
        def __init__(self, injected: object) -> None:
            self.injected = injected

    some_object = object()
    injector.add_injectables(injected=some_object)
    classes = injector.build_classes({"a": A})

    assert classes["a"].injected is some_object
    assert "some_object" not in classes


def test_dependency_injector_resolves_class_dependencies(injector):
    class A:
        def __init__(self) -> None:
            pass

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    classes = injector.build_classes({"a": A, "b": B})

    assert isinstance(classes["a"], A)
    assert isinstance(classes["b"], B)
    assert classes["b"].a is classes["a"]


def test_dependency_injector_saves_instances(injector):
    class A:
        def __init__(self) -> None:
            pass

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    classes = injector.build_classes({"a": A})
    classes2 = injector.build_classes({"b": B})

    assert classes["a"] is classes2["a"]
    assert classes2["b"].a is classes2["a"]


def test_dependency_injector_finds_missing(injector):
    class A:
        def __init__(self, b: object) -> None:
            pass

    with pytest.raises(RuntimeError):
        injector.build_classes({"a": A})


def test_dependency_injector_finds_cycle(injector):
    class A:
        def __init__(self, b: "B") -> None:
            pass

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    with pytest.raises(RuntimeError):
        injector.build_classes({"a": A, "b": B})
