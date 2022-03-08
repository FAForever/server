from unittest import mock

import pytest

from server.weakattr import WeakAttribute


@pytest.fixture(params=("typed", "untyped"))
def obj(request):
    """An object with a WeakAttribute"""
    if request.param == "untyped":
        class Foo(object):
            attr = WeakAttribute()
    else:
        class Foo(object):
            attr = WeakAttribute[mock.Mock]()

    return Foo()


def test_basic(obj):
    ref_obj = mock.Mock()

    assert obj.attr is None

    obj.attr = ref_obj
    assert obj.attr is ref_obj

    del obj.attr
    assert obj.attr is None

    obj.attr = ref_obj
    assert obj.attr is ref_obj

    del ref_obj
    assert obj.attr is None


def test_delete_before_set(obj):
    assert obj.attr is None
    del obj.attr
    assert obj.attr is None
