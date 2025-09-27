import contextlib
import itertools
from functools import wraps
from inspect import Parameter, Signature, iscoroutinefunction, signature


def autocontext(*auto_args):
    """
    Automatically initializes context managers for the scope of a test function.

    Only supports context managers that don't take any arguments, so anything
    that requires the `request` fixture won't work.

    May change the way args and kwargs are passed to the test function.
    """
    def decorate_test(test):
        original_signature = signature(test)
        newsig = new_signature(original_signature, auto_args)

        if iscoroutinefunction(test):
            @wraps(test)
            async def wrapped_test(*args, **kwargs):
                # Tell pytest to omit the body of this function from tracebacks
                __tracebackhide__ = True

                # HACK: @given decorator also modifies function signature
                # in a way that it may pass either only args or only kwargs
                # depending on its internal hackery
                # without @given tests use kwargs
                argvalues = args if args else tuple(kwargs.values())

                with contextlib.ExitStack() as stack:
                    async with contextlib.AsyncExitStack() as astack:
                        fixtures = []
                        for _, arg in zip(auto_args, argvalues):
                            cm = arg()
                            if hasattr(cm, "__aexit__"):
                                fixtures.append(await astack.enter_async_context(cm))
                            else:
                                fixtures.append(stack.enter_context(cm))
                        return await test(*fixtures, *argvalues[len(auto_args):])

            wrapped_test.__signature__ = newsig  # type: ignore[attr-defined]
            return wrapped_test
        else:
            @wraps(test)
            def wrapped_test(*args, **kwargs):
                # Tell pytest to omit the body of this function from tracebacks
                __tracebackhide__ = True

                # HACK: see comment in async version
                argvalues = args if args else tuple(kwargs.values())

                with contextlib.ExitStack() as stack:
                    fixtures = [
                        stack.enter_context(arg())
                        for _, arg in zip(auto_args, argvalues)
                    ]
                    return test(*fixtures, *argvalues[len(auto_args):])

            wrapped_test.__signature__ = newsig  # type: ignore[attr-defined]
            return wrapped_test

    return decorate_test


def new_signature(original_signature: Signature, auto_args):
    """Make an updated signature for the wrapped test."""
    # Replace the parameter names in the original signature with the names
    # of the fixtures given to @autocontext(...) so that pytest will inject the
    # right fixtures.
    new_parameters = tuple(itertools.chain(
        [
            Parameter(name, Parameter.POSITIONAL_OR_KEYWORD)
            for name in auto_args
        ],
        list(original_signature.parameters.values())[len(auto_args):]
    ))
    return original_signature.replace(
        parameters=new_parameters,
        return_annotation=None
    )
