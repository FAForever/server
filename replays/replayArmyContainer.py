import bisect

class replayArmyContainer(object):
    def __init__(self):
        self.__armies = []
        self.__armyId = {}
        
    def __iter__(self):
        for pair in iter(self.__armies):
            yield pair[1]
    
    def __len__(self):
        return len(self.__armies)
    
    def clear(self):
        self.__armies = []
        
    def add(self, army):
        if id(army) in self.__armyId:
            return False
        key = self.key(army.id)
        bisect.insort_left(self.__armies, [key, army])
        self.__armyId[id(army)] = army
        return True
    
    def key(self, id):
        return id
