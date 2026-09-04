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

## Other
-   Mark things as deprecated using a comment like this `# DEPRECATED: <reason>`.
This makes it easy to remove all deprecations by grepping through the project.

# Maintaining

Here are a few notes about how I (Askaholic) have been maintaining this project
written mainly for the benefit of future maintainers.

## Version Numbers

Release version numbers follow [Semantic Versioning](https://semver.org/) with
respect to the commands present in the network protocol as well as the keys
present in those commands. However, the *absence* of a command or key does not
define the protocol API. This means that the addition of new commands or new
parameters to commands is considered a backwards compatible change but their
removal is not. Some commands are also part of a larger "command flow", or
sequence of commands, and the order of that sequence is considered part of the
API. This means that changing the behavior of the server in some way that is not
a simple addition to the protocol is considered a breaking change, with the
exception of changes that are considered bugfixes.

The purpose of this is to create a stable server protocol that will not
spuriously break older client implementations on new releases. Possible
breakages will always happen on a major version update (or possibly if a client
relies on buggy behavior). Still, we should strive to make the transition as
easy as possible by implementing new functionality in a backwards compatible
way and marking the old commands or parameters as deprecated. Ideally, we never
need to release a new client version on the same day as a server update in order
for things to continue functioning.

## Pull Requests

In this repository we squash PR's on merge. The only reason for this is because
the previous maintainer did it when I took over. It doesn't seem to cause too
terrible of a headache because contribution is relatively infrequent, and it
does make the commit history a nice straight line. However, I feel like this
would be more of a hindrance if the rate of PR creation were higher.
