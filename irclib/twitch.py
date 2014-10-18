#imports:
import urllib2
import re
import json
#classes:
class Streamer:

    #constructor:
    def __init__(self, name, mode, link):
        self.name = name
        self.mode = mode
        self.link = link

class Information:

    #constructor:
    def __init__(self, TWITCH_STREAMS, GAME, STREAMER_INFO):
        self.TWITCH_STREAMS = TWITCH_STREAMS
        self.GAME = GAME
        self.STREAMER_INFO = STREAMER_INFO

    def get_game_streamer_names(self):
        "Connects to Twitch.TV API, extracts and returns all streams for a spesific game."

        #start connection
        self.con = urllib2.urlopen(self.TWITCH_STREAMS + self.GAME)
        self.info = self.con.read()
        self.con.close()

        #regular expressions to get all the stream names
        #self.info = re.sub(r'"teams":\[\{.+?"\}\]', '', self.info) #remove all team names (they have the same name: parameter as streamer names)
        #self.streamers_names = re.findall('"name":"(.+?)"', self.info) #looks for the name of each streamer in the pile of info

        self.info = json.loads(self.info) #This will parse the json data as a Python Object
        #Parse the name and return a generator 
        #
        return self.info

    def get_streamer_mode(self, name):
        "Returns a streamers mode (on/off)"

        #start connection
        self.con = urllib2.urlopen(self.STREAMER_INFO + name)
        self.info = self.con.read()
        self.con.close()

        #check if stream is online or offline ("stream":null indicates offline stream)
        if self.info.count('"stream":null') > 0:
            return "offline"
        else:
            return "online"