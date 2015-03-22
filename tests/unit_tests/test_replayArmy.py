from replays.replayArmy import replayArmy

def test_civiliansAreNotPlayers():
    army = replayArmy()
    army.civilian = True
    army.human = True

    assert not army.isPlayer()

def test_nonHumansAreNotPlayers():
    army = replayArmy()
    army.civilian = False
    army.human = False

    assert not army.isPlayer()

def test_nonCivilianHumansArePlayers():
    army = replayArmy()
    army.civilian = False
    army.human = True

    assert army.isPlayer()