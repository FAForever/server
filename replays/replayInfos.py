class replayInfos(object):  # pragma: no cover

    def __init__(self):

        self.description = ''
        self.size = 0
        self.map = ''
        self.cheats = False
        self.teamLock = False
        self.score = True
        self.victory =  'demoralization'
        self.civilian = 'enemy'
        self.Timeouts = -1
        self.FogOfWar = 'explored'
        self.noRush = 'Off'
        self.UnitCap = 500
        self.prebuilt = False
        self.teamSpawn = 'fixed'
        

    def populate(self, infos):
        #print infos
        mapInfo = dict(infos)

        self.description = mapInfo['description']
        self.map = mapInfo['map']
        mapinfoSize = dict(mapInfo['size'])
        self.size = mapinfoSize[1.0]

        options = dict(mapInfo['Options'])
        self.teamLock = options['TeamLock']
        self.score = options['Score']        
        self.victory =  options['Victory']
        self.civilian = options['CivilianAlliance']
        self.Timeouts = options['Timeouts']
        self.FogOfWar = options['FogOfWar']
        self.noRush = options['NoRushOption']
        self.UnitCap = options['UnitCap']
        if options['PrebuiltUnits'] == 'Off':
            self.prebuilt = False
        else: self.prebuild = True
#        self.teamSpawn = mapInfo['description']

    def setCheat(self, value):
        if value == 0:
            self.cheat = False
        else:
            self.cheat = True
        
        
        
    def __str__(self):
        return "%s (%i)" % (self.map, self.size)
