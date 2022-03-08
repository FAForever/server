import asyncio
import contextlib
import inspect
import itertools

from hypothesis.internal.reflection import (
    define_function_signature,
    impersonate
)


def autocontext(*auto_args):
    """
    Automatically initializes context managers for the scope of a test function.

    Only supports context managers that don't take any arguments, so anything
    that requires the `request` fixture won't work.
    """
    def decorate_test(test):
        original_argspec = inspect.getfullargspec(test)
        argspec = new_argspec(original_argspec, auto_args)

        if asyncio.iscoroutinefunction(test):
            @impersonate(test)
            @define_function_signature(test.__name__, test.__doc__, argspec)
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
            @define_function_signature(test.__name__, test.__doc__, argspec)
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


def new_argspec(original_argspec, auto_args):
    """Make an updated argspec for the wrapped test."""
    replaced_args = {
        original_arg: auto_arg
        for original_arg, auto_arg in zip(
            original_argspec.args[:len(auto_args)],
            auto_args
        )
    }
    new_args = tuple(itertools.chain(
        auto_args,
        original_argspec.args[len(auto_args):]
    ))
    annots = {
        replaced_args.get(k) or k: v
        for k, v in original_argspec.annotations.items()
    }
    annots["return"] = None
    return original_argspec._replace(
        args=new_args,
        annotations=annots
    )
