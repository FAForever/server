import copy

import pytest

from server.core import DependencyInjector


@pytest.fixture
def injector():
    return DependencyInjector()


def test_build_classes(injector):
    class A:
        def __init__(self) -> None:
            pass

    class B:
        def __init__(self) -> None:
            pass

    instances = injector.build_classes({"a": A, "b": B})

    assert instances == {
        "a": instances["a"],
        "b": instances["b"]
    }
    assert isinstance(instances["a"], A)
    assert isinstance(instances["b"], B)


def test_build_classes_empty(injector):
    instances = injector.build_classes({})

    assert instances == {}


def test_build_classes_doesnt_modify_input(injector):
    class A:
        def __init__(self) -> None:
            pass

    class B:
        def __init__(self) -> None:
            pass

    classes = {"a": A, "b": B}
    original = copy.deepcopy(classes)

    injector.build_classes(classes, some=A)

    assert classes == original


def test_build_classes_kwargs(injector):
    class A:
        def __init__(self) -> None:
            pass

    class B:
        def __init__(self) -> None:
            pass

    instances = injector.build_classes(a=A, b=B)

    assert instances == {
        "a": instances["a"],
        "b": instances["b"]
    }
    assert isinstance(instances["a"], A)
    assert isinstance(instances["b"], B)


def test_build_twice(injector):
    class A:
        def __init__(self) -> None:
            pass

    instances = injector.build_classes({"a": A})
    instances2 = injector.build_classes({"a": A})

    assert instances == {"a": instances["a"]}
    assert instances2 == {"a": instances2["a"]}
    assert instances["a"] is instances2["a"]


def test_resolve_dependencies(injector):
    class A:
        def __init__(self, injected: object) -> None:
            self.injected = injected

    some_object = object()
    injector.add_injectables({"injected": some_object})
    instances = injector.build_classes({"a": A})

    assert instances == {"a": instances["a"]}
    assert instances["a"].injected is some_object


def test_resolve_dependencies_kwargs(injector):
    class A:
        def __init__(self, injected: object) -> None:
            self.injected = injected

    some_object = object()
    injector.add_injectables(injected=some_object)
    instances = injector.build_classes({"a": A})

    assert instances == {"a": instances["a"]}
    assert instances["a"].injected is some_object


def test_resolve_class_dependencies(injector):
    class A:
        def __init__(self) -> None:
            pass

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    instances = injector.build_classes({"a": A, "b": B})

    assert instances == {
        "a": instances["a"],
        "b": instances["b"]
    }
    assert isinstance(instances["a"], A)
    assert isinstance(instances["b"], B)
    assert instances["b"].a is instances["a"]


def test_save_instances(injector):
    class A:
        def __init__(self) -> None:
            pass

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    instances = injector.build_classes({"a": A})
    instances2 = injector.build_classes({"a": A, "b": B})

    assert instances == {"a": instances["a"]}
    assert instances2 == {
        "a": instances2["a"],
        "b": instances2["b"]
    }
    assert instances["a"] is instances2["a"]
    assert instances2["b"].a is instances2["a"]


def test_find_missing(injector):
    class A:
        def __init__(self, b: object) -> None:
            pass

    with pytest.raises(RuntimeError):
        injector.build_classes({"a": A})


def test_find_cycle(injector):
    class A:
        def __init__(self, b: "B") -> None:
            pass

    class B:
        def __init__(self, a: A) -> None:
            self.a = a

    with pytest.raises(RuntimeError):
        injector.build_classes({"a": A, "b": B})
