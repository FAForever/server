class ReplayArmy(object):  # pragma: no cover
    def __init__(self):

        self.color = 0
        self.civilian = False
        self.faction = 1
        self.id = ''
        self.team = 0
        self.human = True

    def populate(self, infos):
        armyInfo = dict(infos)
        self.color = armyInfo['PlayerColor']
        self.civilian = armyInfo['Civilian']
        self.faction = armyInfo['Faction']
        self.id = armyInfo['PlayerName']
        self.team = armyInfo['Team']
        self.human = armyInfo['Human']

    def is_player(self):
        return not self.civilian and self.human
        
    def __str__(self):
        return "%s : team (%i)" % (self.id, self.team)
