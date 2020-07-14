# Contributing

When contributing for the first time, try to find an issue labeled with
[good first issue](https://github.com/FAForever/server/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22),
and leave a comment stating that you would like to work on
it, that way we can assign it to you. Fork this repository and base your pull
request on the `develop` branch. Note that we squash on merge, so pull requests
that have been open for a while may need to be rebased before they can be merged.

## Pull Request Process

1.  Create a branch on your fork based on `develop`. Our convention is to name
branches like `issue/#123-fix-thing`, or `feature/#456-add-thing` depending on
whether the referenced issue pertains to a bug or an enhancement.
2.  Before committing, make sure that the unit tests pass, and that you have
checked your code with a linter.
    1. Check changes with [flake8](https://pypi.org/project/flake8/).
    2. Sort imports with [isort](https://pypi.org/project/isort/), our settings
    are already checked into the setup.cfg file.
    3. Run all tests with `pipenv run tests`.
3.  Open a pull request with the issue number in the title, and `Closes #123` in
the description. GitHub will default the title to the name of your branch, but
feel free to expand it a little if you have the space, e.g. `Issue/#123 Fix this
one thing` or `Feature/#456 add that other thing`.

### Committing

Use the normal git conventions for commit messages, with the following rules:
-   Subject line shorter than 80 characters
-   Proper capitalized sentence as subject line, with no trailing period
-   For non-trivial commits, include a commit message body, describing the
change in detail

For further tips on writing good commit messages have a read through
[this post](https://chris.beams.io/posts/git-commit/#seven-rules).

## Code Style

Historically, this project has lacked an established coding style, so the
formatting may be inconsistent in places. If you are unsure of how to format
something, ask one of the maintainers, but here are some rules we have been
working on adopting:

1.  Use double quotes for strings unless single quotes are absolutely necessary
to increase readability i.e. in order to reduce the number of backslash escapes.
2.  When splitting function calls/definitions over multiple lines, place
arguments/parameters on an indented newline. Examples:

```python
def some_long_function_name_with_many_parameters(
    parameter_number_one,
    parameter_number_two,
    parameter_number_three,
):
    pass

some_long.function_name_with_many_args(
    argument_number_one,
    argument_number_two,
    argument_number_three,
    {
        "key1", "value1",
        "key2": "value2"
    },
)
some_long.function_name_with_dict_arg({
    "key1", "value1",
    "key2": "value2",
})
```

3.  Keep lines shorter than 80 characters. This rule is somewhat lenient.
4.  More to come...
