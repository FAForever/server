import asyncio
import contextlib
import itertools
from inspect import Parameter, Signature

import pytest
from hypothesis.internal.reflection import (
    define_function_signature,
    get_signature,
    impersonate
)


def autocontext(*auto_args):
    """
    Automatically initializes context managers for the scope of a test function.

    Only supports context managers that don't take any arguments, so anything
    that requires the `request` fixture won't work.
    """
    def decorate_test(test):
        original_signature = get_signature(test)
        signature = new_signature(original_signature, auto_args)

        if asyncio.iscoroutinefunction(test):
            @pytest.mark.asyncio
            @impersonate(test)
            @define_function_signature(test.__name__, test.__doc__, signature)
            async def wrapped_test(*args, **kwargs):
                # Tell pytest to omit the body of this function from tracebacks
                __tracebackhide__ = True

                with contextlib.ExitStack() as stack:
                    async with contextlib.AsyncExitStack() as astack:
                        fixtures = []
                        for _, arg in zip(auto_args, args):
                            cm = arg()
                            if hasattr(cm, "__aexit__"):
                                fixtures.append(
                                    await astack.enter_async_context(cm)
                                )
                            else:
                                fixtures.append(
                                    stack.enter_context(cm)
                                )

                        return await test(
                            *tuple(itertools.chain(
                                fixtures,
                                args[len(auto_args):]
                            )),
                            **kwargs
                        )

            return wrapped_test
        else:
            @impersonate(test)
            @define_function_signature(test.__name__, test.__doc__, signature)
            def wrapped_test(*args, **kwargs):
                # Tell pytest to omit the body of this function from tracebacks
                __tracebackhide__ = True

                with contextlib.ExitStack() as stack:
                    fixtures = [
                        stack.enter_context(arg())
                        for _, arg in zip(auto_args, args)
                    ]
                    return test(
                        *tuple(itertools.chain(
                            fixtures,
                            args[len(auto_args):]
                        )),
                        **kwargs
                    )

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
