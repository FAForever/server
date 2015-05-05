from challonge import api


def index(**params):
    """Retrieve a set of tournaments created with your account."""
    return api.fetch_and_parse("GET", "tournaments", **params)


def create(name, url, tournament_type="single elimination", **params):
    """Create a new tournament."""
    params.update({
        "name": name,
        "url": url,
        "tournament_type": tournament_type,
    })

    return api.fetch_and_parse("POST", "tournaments", "tournament", **params)


def show(tournament):
    """Retrieve a single tournament record created with your account."""
    return api.fetch_and_parse("GET", "tournaments/%s" % tournament)


def update(tournament, **params):
    """Update a tournament's attributes."""
    api.fetch("PUT", "tournaments/%s" % tournament, "tournament", **params)


def destroy(tournament):
    """Deletes a tournament along with all its associated records.

    There is no undo, so use with care!

    """
    api.fetch("DELETE", "tournaments/%s" % tournament)


def publish(tournament):
    """Publish a tournament, making it publically accessible.

     The tournament must have at least 2 participants.

     """
    api.fetch("POST", "tournaments/publish/%s" % tournament)


def start(tournament):
    """Start a tournament, opening up matches for score reporting.

    The tournament must have at least 2 participants.

    """
    api.fetch("POST", "tournaments/start/%s" % tournament)


def reset(tournament):
    """Reset a tournament, clearing all of its scores and attachments.

    You can then add/remove/edit participants before starting the
    tournament again.

    """
    api.fetch("POST", "tournaments/reset/%s" % tournament)
