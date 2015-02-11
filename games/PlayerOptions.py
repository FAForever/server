
class PlayerOptions(object):
    def __init__(self):
        self.options = {}

    def __getitem__(self, key):
        if key not in self.options:
            self.options[key] = {}
        return self.options[key]

    def move(self, origin, target):
        self.options[target] = self.options[origin]
        del self.options[origin]
