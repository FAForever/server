from challonge import api


def index(tournament):
    """Retrieve a tournament's participant list."""
    return api.fetch_and_parse(
        "GET",
        "tournaments/%s/participants" % tournament)

def create(tournament, name, **params):
    """Add a participant to a tournament."""
    params.update({"name": name})

    return api.fetch_and_parse(
        "POST",
        "tournaments/%s/participants" % tournament,
        "participant",
        **params)


def show(tournament, participant_id):
    """Retrieve a single participant record for a tournament."""
    return api.fetch_and_parse(
        "GET",
        "tournaments/%s/participants/%s" % (tournament, participant_id))


def update(tournament, participant_id, **params):
    """Update the attributes of a tournament participant."""
    api.fetch(
        "PUT",
        "tournaments/%s/participants/%s" % (tournament, participant_id),
        "participant",
        **params)


def destroy(tournament, participant_id):
    """Destroys or deactivates a participant.

    If tournament has not started, delete a participant, automatically
    filling in the abandoned seed number.

    If tournament is underway, mark a participant inactive, automatically
    forfeiting his/her remaining matches.

    """
    api.fetch(
        "DELETE",
        "tournaments/%s/participants/%s" % (tournament, participant_id))


def randomize(tournament):
    """Randomize seeds among participants.

    Only applicable before a tournament has started.

    """
    api.fetch("POST", "tournaments/%s/participants/randomize" % tournament)
