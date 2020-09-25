import mock

from server.core import Service


def test_service_registry():
    with mock.patch("server.core.service.service_registry", {}) as registry:
        class Foo(Service):
            pass

        assert registry["foo"] is Foo
        assert registry == {"foo": Foo}


def test_service_registry_name_override():
    with mock.patch("server.core.service.service_registry", {}) as registry:
        class Foo(Service, name="FooService"):
            pass

        assert registry["FooService"] is Foo
        assert registry == {"FooService": Foo}
