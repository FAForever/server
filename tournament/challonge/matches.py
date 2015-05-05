from challonge import api


def index(tournament, **params):
    """Retrieve a tournament's match list."""
    return api.fetch_and_parse(
        "GET",
        "tournaments/%s/matches" % tournament,
        **params)


def show(tournament, match_id):
    """Retrieve a single match record for a tournament."""
    return api.fetch_and_parse(
        "GET",
        "tournaments/%s/matches/%s" % (tournament, match_id))


def update(tournament, match_id, **params):
    """Update/submit the score(s) for a match."""
    api.fetch(
        "PUT",
        "tournaments/%s/matches/%s" % (tournament, match_id),
        "match",
        **params)
