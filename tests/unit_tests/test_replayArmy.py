from replays.replay_army import ReplayArmy

def test_civiliansAreNotPlayers():
    army = ReplayArmy()
    army.civilian = True
    army.human = True

    assert not army.is_player()

def test_nonHumansAreNotPlayers():
    army = ReplayArmy()
    army.civilian = False
    army.human = False

    assert not army.is_player()

def test_nonCivilianHumansArePlayers():
    army = ReplayArmy()
    army.civilian = False
    army.human = True

    assert army.is_player()
