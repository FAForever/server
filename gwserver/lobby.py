#-------------------------------------------------------------------------------
# Copyright (c) 2014 Gael Honorez.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#-------------------------------------------------------------------------------


from PySide import QtCore, QtNetwork
from PySide.QtSql import QSqlQuery

from types import *

import logging
import json
import random
import time
import hashlib
import os
import copy
import base64
from . import phpserialize
import math
from .teams import teams

AUTORECALL = 500


ranksRequirement = {
1 : {"money" : 200, "victories" : 0 },
2 : {"money" : 300, "victories" : 10 },
3 : {"money" : 400, "victories" : 20 },
4 : {"money" : 500, "victories" : 30 },
5 : {"money" : 600, "victories" : 40 },
6 : {"money" : 700, "victories" : 50 },
7 : {"money" : 1000, "victories" : 60 }
}


from configobj import ConfigObj
config = ConfigObj("/etc/faforever/faforever.conf")
TEXPATH = config['global']['content_path'] + "/images"

FACTIONS = {0:"uef", 1:"aeon", 2:"cybran", 3:"seraphim"}
CONTROL_THRESHOLD = 0.9
ATTACK_THRESHOLD = 0.5

INITIAL_CREDITS = 0
COST_ATTACK     = 100

ATTACK_PERDIOD = 10

PLANET_VERTEX_SRC = """
const float Eta = 1.1;         // Ratio of indices of refraction
const float FresnelPower = 2.5;

const float F  = ((1.0-Eta) * (1.0-Eta)) / ((1.0+Eta) * (1.0+Eta));

varying vec3 normal, halfVector;
varying float Ratio;


uniform vec3 pos;         // Position de la sphere dans le repere Objet
uniform vec3 scaling;
attribute highp vec3 camPos;         // Position de la sphere dans le repere Objet
attribute lowp float rotation;


void main(void)
{
    vec4 a = gl_Vertex; 
    a.x = a.x * scaling.x;
    a.y = a.y * scaling.y;
    a.z = a.z * scaling.z;

    gl_TexCoord[0] = gl_MultiTexCoord0;

    vec3 look = normalize(camPos - pos);
    vec3 upVector = vec3(1.0, 0.0, 0.0);

    vec3 r = cross ( upVector, look );
    vec3 up = cross ( look, r );

    mat4 RotationMatrixDir = mat4( vec4(cos(-1.53),     0.0, sin(-1.53),     0.0),
                              vec4(0.0,         1.0, 0.0,             0.0),
                              vec4(-sin(-1.53), 0.0, cos(-1.53),     0.0),
                              vec4(0.0,         0.0, 0.0,             1.0)); 

    mat4 RotationMatrixDir2 = mat4(1.0, 0.0, 0.0, 0.0,
                                     0.0, cos(rotation), -sin(rotation), 0.0,
                                     0.0, sin(rotation), cos(rotation), 0.0,
                                     0.0, 0.0, 0.0, 1.0); 

    mat4 billboard = mat4(
                     vec4(r.x, up.x, look.x, pos.x),
                       vec4(r.y, up.y, look.y, pos.y),
                       vec4(r.z, up.z, look.z, pos.z),
                       vec4(0, 0, 0, 1.0)                             
                    );


    mat4 finalPosMtx = RotationMatrixDir *RotationMatrixDir2 * billboard;
    normal = vec3(normalize(vec4(gl_Normal ,1)* RotationMatrixDir *RotationMatrixDir2));
    vec4 ecPosition  = gl_ModelViewMatrix * a *finalPosMtx;
    vec3 i = vec3(normalize(ecPosition - gl_ModelViewMatrix*vec4(camPos,1)));   
    Ratio   = F + (1.0 - F) * pow(1.0 - normal.z, FresnelPower);

    halfVector =  normalize(vec3(gl_LightSource[0].halfVector.xyz));
    gl_Position = gl_ProjectionMatrix * gl_ModelViewMatrix * (a * finalPosMtx);

}
"""

PLANET_FRAGMENT_SRC = """
varying vec3 normal, halfVector;

varying mat4 billboard, RotationMatrixDir, RotationMatrixDir2;
varying float Ratio;
varying vec4 lightDir;
uniform sampler2D texture;
vec4 light0 ()
{

  vec4 color;
  
  vec4 ambient = gl_LightSource[0].ambient * gl_FrontMaterial.ambient;
  vec4 diffuse = gl_LightSource[0].diffuse * max(dot(vec4(normal,0),gl_LightSource[0].position),0.0) * gl_FrontMaterial.diffuse;
  color = ambient + diffuse;
  return color;
}
 
vec4 light1 ()
{

  vec4 color;
  
  vec4 ambient = gl_LightSource[1].ambient * gl_FrontMaterial.ambient;
  vec4 diffuse = gl_LightSource[1].diffuse * max(dot(vec4(normal,0),gl_LightSource[1].position),0.0) * gl_FrontMaterial.diffuse;
  color = ambient + diffuse;
  return color;
}


void main (void)
{

    vec4 texture_color = texture2D(texture,vec2(gl_TexCoord[0]));

    float shiny = gl_FrontMaterial.shininess;
    
    vec3 N = normalize(normal);
    
    float NdotHV = max(0.0,dot( N,(halfVector) ));
    
    
    vec4 spec = gl_LightSource[0].specular * 
                       gl_FrontMaterial.specular * 
                        pow( NdotHV , shiny );

   vec4 diffuse_light = vec4(0.0, 0.0, 0.0, 1.0);
 
  if(vec3(gl_LightSource[0].position) != vec3(0.0, 0.0, 0.0))
    diffuse_light += light0();
  if(vec3(gl_LightSource[1].position) != vec3(0.0, 0.0, 0.0))
    diffuse_light += light1();
 
    gl_FragColor =  (diffuse_light * texture_color) + spec + (diffuse_light *1.8 *  Ratio);
    gl_FragColor.a = 1.0; 
}
"""



BACK_FRAGMENT_SRC  = """
uniform sampler2D texture;
void main (void)
{
    gl_FragColor = texture2D(texture,vec2(gl_TexCoord[0])) ;
}
"""

STARS_VERTEX_SRC = """
void main(void)
{
    gl_TexCoord[0] = gl_MultiTexCoord0;
    gl_Position = ftransform();        
}
"""

STARS_FRAGMENT_SRC = """
uniform sampler2D texture;
void main (void)
{  
    gl_FragColor = gl_FrontMaterial.diffuse ;    
    gl_FragColor.a = pow(texture2D(texture,vec2(gl_TexCoord[0]))[0],2.0) * gl_FrontMaterial.diffuse.a;
}
"""


CONSTANT_VERTEX_SRC = """
void main(void)
{
    gl_Position = ftransform();        
}
"""

CONSTANT_FRAGMENT_SRC = """
void main (void)
{
    gl_FragColor = gl_FrontMaterial.diffuse ;
}
"""

SELECTION_VERTEX_SRC = """
attribute highp vec3 camPos;         // Position de la sphere dans le repere Objet
attribute highp vec3 pos;         // Position de la sphere dans le repere Objet
attribute highp vec3 scaling;

void main(void)
{
    vec4 a = gl_Vertex; 
    a.x = a.x * scaling.x;
    a.y = a.y * scaling.y;
    a.z = a.z * scaling.z;
    vec3 look = normalize(camPos - pos);
    vec3 upVector = vec3(1.0, 0.0, 0.0);
    vec3 r = cross ( upVector, look );
    vec3 up = cross ( look, r );

    float angle = -90.0 * 0.017;

    mat4 RotationMatrixDir = mat4( vec4(cos(angle),     0.0, sin(angle),     0.0),
                              vec4(0.0,         1.0, 0.0,             0.0),
                              vec4(-sin(angle), 0.0, cos(angle),     0.0),
                              vec4(0.0,         0.0, 0.0,             1.0)); 

    mat4 billboard = mat4(
                     vec4(r.x, up.x, look.x, pos.x),
                       vec4(r.y, up.y, look.y, pos.y),
                       vec4(r.z, up.z, look.z, pos.z),
                       vec4(0, 0, 0, 1.0)                             
                    );

    gl_TexCoord[0] = gl_MultiTexCoord0;
    
    mat4 finalPosMtx =  billboard;
    gl_Position = gl_ProjectionMatrix * gl_ModelViewMatrix * (a * finalPosMtx);    
}
"""

ATMOSPHERE_VERTEX_SRC = """
uniform vec3 pos;         // Position de la sphere dans le repere Objet
attribute highp vec3 camPos;         // Position de la sphere dans le repere Objet
uniform vec3 scaling;

void main(void)
{
      vec4 a = gl_Vertex; 
    a.x = a.x * scaling.x;
    a.y = a.y * scaling.y;
    a.z = a.z * scaling.z;
    vec3 look = normalize(camPos - pos);
    vec3 upVector = vec3(1.0, 0.0, 0.0);
    vec3 r = cross ( upVector, look );
    vec3 up = cross ( look, r );

    float angle = -90.0 * 0.017;

    mat4 RotationMatrixDir = mat4( vec4(cos(angle),     0.0, sin(angle),     0.0),
                              vec4(0.0,         1.0, 0.0,             0.0),
                              vec4(-sin(angle), 0.0, cos(angle),     0.0),
                              vec4(0.0,         0.0, 0.0,             1.0)); 

    mat4 billboard = mat4(
                     vec4(r.x, up.x, look.x, pos.x),
                       vec4(r.y, up.y, look.y, pos.y),
                       vec4(r.z, up.z, look.z, pos.z),
                       vec4(0, 0, 0, 1.0)                             
                    );

    gl_TexCoord[0] = gl_MultiTexCoord0;
    
    mat4 finalPosMtx =  billboard;
    gl_Position = gl_ProjectionMatrix * gl_ModelViewMatrix * (a * finalPosMtx);    
}
"""

ATMOSPHERE_FRAGMENT_SRC = """
uniform sampler2D texture;
void main (void)
{
    gl_FragColor.r = .7 ;    
    gl_FragColor.g = .8 ;
    gl_FragColor.b = 1.0 ;
    gl_FragColor.a = pow(texture2D(texture,vec2(gl_TexCoord[0]))[0],3.0);
}
"""


SWIRL_VERTEX_SRC = """
uniform vec3 pos;         // Position de la dans le repere Objet
uniform vec3 rotation;
uniform vec3 scaling;
attribute lowp float rotation_plane;


void main(void)
{
    vec4 a = gl_Vertex; 
    a.x = a.x * scaling.x;
    a.y = a.y * scaling.y;
    a.z = a.z * scaling.z;
    vec3 look = vec3(0.0, 0.0, 1.0);
    vec3 upVector = vec3(1.0, 0.0, 0.0);
    vec3 r = cross ( upVector, look );
    vec3 up = cross ( look, r );

    float angle = rotation_plane + rotation.x; 


    mat4 RotationMatrixDir = mat4(cos(angle), -sin(angle), 0.0, 0.0,
                                     sin(angle), cos(angle), 0.0 , 0.0,
                                     0.0, 0.0 , 1.0, 0.0,
                                     0.0, 0.0, 0.0, 1.0); 

    mat4 billboard = mat4(
                     vec4(r.x, up.x, look.x, pos.x),
                       vec4(r.y, up.y, look.y, pos.y),
                       vec4(r.z, up.z, look.z, pos.z),
                       vec4(0, 0, 0, 1.0)                             
                    );

    gl_TexCoord[0] = gl_MultiTexCoord0;
    
    mat4 finalPosMtx =  RotationMatrixDir *billboard;
  
    
    gl_Position = gl_ProjectionMatrix * gl_ModelViewMatrix * (a * finalPosMtx);    
}
"""





class ClientModule(QtCore.QObject):
    def __init__(self, socket, parent=None):
        super(ClientModule, self).__init__(parent)
        
        self.log = logging.getLogger(__name__)
        
        self.parent = parent        
        self.db = self.parent.db
            
        self.session = random.getrandbits(32)
        

        self.socket = QtNetwork.QTcpSocket(self)
        self.socket.setSocketDescriptor(socket)

        self.user       = None
        self.uid        = None
        self.avataruid  = None
        self.faction    = None
        self.name       = None
        self.rank       = 0
        self.victories  = 0
        self.credits    = 0
        self.inBattle   = False
        self.away = False
        
        self.logged = False    
        
        self.dominatedBy = None
        self.dominating = None
        
        self.attackList = {}
            
        self.ip = self.socket.peerAddress().toString()
        self.port = self.socket.peerPort()
        self.peerName = self.socket.peerName()
    
        self.requestid = {}

        self.socket.readyRead.connect(self.readDatas)
        #self.socket.setSocketOption(QtNetwork.QTcpSocket.KeepAliveOption, 1)
        self.socket.disconnected.connect(self.disconnection)
        self.socket.error.connect(self.displayError)
        self.blockSize = 0


        self.pingTimer = None
        self.ponged = False
        self.missedPing = 0
        
        self.user = None

    def ping(self):
        if hasattr(self, "socket"):
            if self.ponged == False :
                if self.missedPing > 2 :
                    if self.uid:
                        self.log.debug("missing two pings, aborting %i" % self.uid)
                    self.socket.abort()
                            
                else :  
                    self.sendReply("PING")
                    self.missedPing = self.missedPing + 1
            else :    
                self.sendReply("PING")
                self.ponged = False
                self.missedPing = 0

    def sendNews(self):
        self.sendJSON(dict(command="news_feed", news = self.parent.newsFeed.getNews()))
        

    def sendPlanet(self, uid):
        planet = self.parent.planets[uid]
        if planet["visible"] == True:
            mapname = planet["mapname"].split("/")[1][:-4]
            self.sendJSON(dict(command="planet_info", sector = planet["sector"], uid = planet["uid"], posx = planet["posx"], posy = planet["posy"], size = planet["size"], name = planet["name"], desc = planet["desc"], uef = planet["uef"], cybran = planet["cybran"], aeon = planet["aeon"], seraphim = planet["seraphim"], links = planet["links"], texture = planet["texture"], md5tex = planet["md5tex"], mapname=mapname, visible=planet["visible"], maxplayer=planet["maxplayer"]))            
        else:
            self.sendJSON(dict(command="planet_info", sector = planet["sector"], uid = planet["uid"], posx = planet["posx"], posy = planet["posy"], size = planet["size"], name = planet["name"], desc = planet["desc"], uef = planet["uef"], cybran = planet["cybran"], aeon = planet["aeon"], seraphim = planet["seraphim"], links = planet["links"], texture = planet["texture"], md5tex = planet["md5tex"], visible=planet["visible"]))

        
        
    def sendDefense(self, planetuid, check=False):
        defenses = self.parent.planetaryDefenses.getDefenses(planetuid, check)
        if len(defenses) == 0:
            self.sendJSON(dict(command="planet_defense_remove", planetuid=planetuid))
        else:
            for item in defenses:            
                self.sendJSON(item)
        
    def sendDepot(self, planetuid):
        depot = self.parent.depots.getDepot(planetuid)
        if depot:
            self.sendJSON(depot)
        
    def sendDepots(self):
        self.parent.depots.update()
        for uid in self.parent.planets :
            self.sendDepot(uid)
    
    def sendDefenses(self, check=False):
        self.parent.updateGalaxy()
        for uid in self.parent.planets :
            self.sendDefense(uid, check)
                    
    def sendPlanets(self):
        self.log.debug("sending planets")
        self.parent.updateGalaxy()
        
        for uid in self.parent.planets :
            
            self.sendPlanet(uid)
        
    def sendAttacks(self, update = True):
        if self.logged == False:
            return
        #self.log.debug("sending attack list")
        if update :
            self.parent.updateAttackList()
        
        self.sendJSON(dict(command="attacks_info", attacks=self.parent.attacks.getList(self.rank)))

    
    def sendEndInit(self):
        self.sendJSON(dict(command="init_done", status = True ))

    def getMd5(self, fileName):
        '''
        Compute md5 hash of the specified file.
        '''
        m = hashlib.md5()
        if not os.path.isfile(fileName): return None
        
        fd = open(fileName, "rb")
        while True:
            #read the file in 1 MiB chunks, this requires less memory in case one day we need to read something big, like textures.scd or units.scd
            content = fd.read(1024*1024) 
            if not content: break
            m.update(content)
        fd.close()
            
        return m.hexdigest()    
    
    def get_name(self):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT * FROM `avatars` WHERE uid = ? AND alive = 1")
        query.addBindValue(self.uid)
        query.exec_()
        if query.size() == 1 :
            query.first()
            self.avataruid  = int(query.value(7))
            self.name       = str(query.value(1)) 
            self.rank       = int(query.value(2))
            self.victories  = int(query.value(3))
            self.credits    = int(query.value(4))
            return True    
        else :
            name = ""
            self.rank = 0
            if self.faction == 0 :
                from .namegenerator import uef
                name = uef.generateName()
            elif self.faction == 1 :
                from .namegenerator import aeon
                name = aeon.generateName()
            elif self.faction == 2 :
                from .namegenerator import cybran
                name = cybran.generateName()
            elif self.faction == 3 :
                from .namegenerator import seraphim
                name = seraphim.generateName()
            
            self.name = name 
               
            self.sendJSON(dict(command="create_account", action = 1, name = name, rank = 0, faction = self.faction))
            return False

    def loggedIn(self):
        #TODO:remove all the infos from logged_in
        self.sendJSON(dict(command="logged_in", uid = self.uid, name = self.name, faction = self.faction, rank = self.rank, victories = self.victories, credits = self.credits))

        # check if this faction is dominated
        if self.parent.domination.isDominated(self.faction):           
            self.dominatedBy = self.parent.domination.getDominant(self.faction)
            self.sendJSON(dict(command="domination", master = self.dominatedBy))

        if self.dominatedBy != None :
            self.sendJSON(dict(command="social", autojoin=self.dominatedBy))
        else:
            self.sendJSON(dict(command="social", autojoin=self.faction))    
        self.updatePlayerStats()
        
        if not self.uid in self.parent.factionPlayers[self.faction][self.rank] : 
            self.parent.factionPlayers[self.faction][self.rank].append(self.uid)
        self.logged = True
        
        self.sendAttacks()
        self.sendNews()
        self.pingTimer = QtCore.QTimer(self)                              
        self.pingTimer.timeout.connect(self.ping)
        self.pingTimer.start(61000)


    def isAvailableForBattle(self):
        if self.inBattle == False and self.away == False :
            return True
        return False
        

    def updateCredits(self):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT credits FROM `avatars` WHERE uid = ? AND alive = 1")
        query.addBindValue(self.uid)
        query.exec_()
        if query.size() == 1 :
            query.first()
            self.credits    = int(query.value(0))            

    def removeCredits(self, value):
        query = QSqlQuery(self.parent.db)
        query.prepare("UPDATE `avatars` SET `credits` = (`credits`-?) WHERE uid = ? AND alive = 1")
        query.addBindValue(value)
        query.addBindValue(self.uid)
        query.exec_()
        self.updatePlayerStats()

    def addCredits(self, value):
        query = QSqlQuery(self.parent.db)
        query.prepare("UPDATE `avatars` SET `credits` = (`credits`+?) WHERE uid = ? AND alive = 1")
        query.addBindValue(value)
        query.addBindValue(self.uid)
        query.exec_()
        self.updatePlayerStats()

    def updateAttackList(self, planetuid):
        query = QSqlQuery(self.parent.db)
        query.prepare("INSERT INTO `attacks` (uid_player, uid_planet) VALUES (?,?)")
        query.addBindValue(self.uid)
        query.addBindValue(planetuid)
        query.exec_()
        self.parent.updateAttackList()
        self.parent.sendAttackToAll()

    def getCombatFaction(self):
        if self.dominatedBy != None :
            return self.dominatedBy
        else:
            return self.faction 

    def command_quit_squad(self, message):
        '''We want to quit our squad'''
        #inform all members
        leader = self.parent.teams.getSquadLeader(self.uid)
        if not leader:
            return
        members = self.parent.teams.getAllMembers(leader)
        
        if leader == self.uid:
            self.parent.teams.disbandSquad(leader)
            for conn in self.parent.recorders:
                if conn.uid in members:
                    conn.sendJSON(dict(command="remove_team"))

            didSomething = False
            for memberid in members:
                planetuids = self.parent.attacks.cleanGames(memberid)
                if len(planetuids) >0:
                    didSomething = True
                    for planetuid in planetuids:
                        self.parent.attacks.removePlayer(planetuid,  memberid)
                    
            if didSomething:
                self.parent.updateAttackList()
                self.parent.sendAttackToAll()    
           
        else:
            self.parent.teams.removeFromSquad(leader, self.uid)
            planetuids = self.parent.attacks.cleanGames(self.uid)
            didSomething = False
            if len(planetuids) >0:
                didSomething = True
                for planetuid in planetuids:
                    self.parent.attacks.removePlayer(planetuid, self.uid)
            if didSomething:
                self.parent.updateAttackList()
                self.parent.sendAttackToAll()               
            
            newmembers = self.parent.teams.getAllMembers(leader)
            if len(newmembers) == 1:
                self.parent.teams.disbandSquad(leader)
                
            for conn in self.parent.recorders:
                if conn.uid in members:
                    if conn.uid == self.uid or len(newmembers) == 1:
                        conn.sendJSON(dict(command="remove_team"))
                    else:                           
                        conn.sendJSON(dict(command="team", leader=leader, members=newmembers))
        

                
    
    def command_accept_team_proposal(self, message):
        '''we have accepted a team proposal'''
        leader = message["uid"]

        # first, check if the leader is in a squad...
        if self.parent.teams.isInSquad(leader):
            # if so, check if he is the leader already
            if not self.parent.teams.isLeader(leader):
                #if he is not a leader, we can't accept.
                return

        squadMembers = self.parent.teams.getAllMembers(leader)
        # check if the squad has place left
        if len(squadMembers) >= 4:
            self.sendJSON(dict(command="notice", style="info", text="Sorry, the squad is full."))   
            return
   
        if self.parent.teams.addInSquad(leader, self.uid):
            if self.parent.cleanGames(leader):
                for conn in self.parent.recorders:
                    if conn.uid == leader:
                        conn.sendJSON(dict(command="notice", style="info", text="Someone joined your squad. Your current attacks are cancelled."))
                        break                 
            
            #first clean the games
            if self.parent.cleanGames(self.uid):
                self.sendJSON(dict(command="notice", style="info", text="You have joined your squad. Your current attacks are cancelled."))
            # success, we can inform all the squad members
            members = self.parent.teams.getAllMembers(leader)
            for conn in self.parent.recorders:
                if conn.uid in members:
                    conn.sendJSON(dict(command="team", leader=leader, members=members))

    def command_request_team(self, message):
        ''' Request a player for making a team '''
        uid = message["uid"]
        #check how many players are in the squad currently
        squadSize = len(self.parent.teams.getAllMembers(uid))
        if  squadSize >= 4:
            self.sendJSON(dict(command="notice", style="info", text="Squads can have maximum 4 players."))
            return
     
            
        if self.parent.teams.isInSquad(uid):
            self.sendJSON(dict(command="notice", style="info", text="The player is already in a squad."))
            return

        #check for current attack and squad size
        if squadSize:
            attacks = self.parent.attacks.getAttackFrom(self.uid)
            if len(attacks) > 0:
                for attack in attacks:
                    #check the size of the planet.....
                    query = QSqlQuery(self.parent.db)
                    query.prepare("SELECT max_players FROM planet_maps LEFT JOIN faf_lobby.table_map ON faf_lobby.table_map.id = planet_maps.mapuid WHERE planetuid = ?")
                    query.addBindValue(attack)
                    query.exec_()
                    if query.size > 0:
                        query.first()
                        planetSize = int(query.value(0)) / 2
                        if squadSize+1 > planetSize:
                            self.sendJSON(dict(command="notice", style="info", text= ("The planet currently attacked is too small to add someone.")))
                            return False           
        
        for conn in self.parent.recorders:
            if conn.uid == uid and conn.away == False:
                conn.sendJSON(dict(command="request_team", uid=self.uid, who=self.user["login"]))
                break

    def command_get_player_list(self, message):
        ''' send the whole player list in our faction '''
        playerList = {}
        for conn in self.parent.recorders:
            if conn.faction == None :
                continue
            if  conn.faction == self.faction or conn.faction == self.dominatedBy or conn.dominatedBy == self.faction:
                if conn.user != None:
                    playerList[conn.user["login"]]=conn.uid
        
        self.sendJSON(dict(command="faction_player_list", players=playerList))

    def groupDeleted(self, group):
        '''inform the player that a group is deleted'''
        self.sendJSON(dict(command="group_reinforcements_deleted", group=group))
        

    def command_move_reinforcement_group(self, message):
        ''' move stuff around '''
        itemuid     = message["itemuid"]
        origin      = message["origin"]
        destination = message["destination"]
        amount      = message["amount"]
        
        fromAmount = 0
        
        # first, remove the amount from origin, and check if we have that many!
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT amount FROM `reinforcements_groups` WHERE `userId`= ? AND `group` = ? AND `unit` = ?")
        query.addBindValue(self.uid)
        query.addBindValue(origin)
        query.addBindValue(itemuid)
        if not query.exec_():
            self.log.warning(query.lastError())
        if query.size() > 0:
            query.first()
            fromAmount = int(query.value(0))
            
        if fromAmount < amount:
            # we have not enough.
            return

        newAmount = fromAmount - amount
        if newAmount <= 0:
            query = QSqlQuery(self.parent.db)
            query.prepare("DELETE FROM `reinforcements_groups` WHERE `userId`=? AND `group` = ? AND `unit` = ?")
            query.addBindValue(self.uid)
            query.addBindValue(origin)
            query.addBindValue(itemuid)
            if not query.exec_():
                self.log.warning(query.lastError())            
        else:
            query = QSqlQuery(self.parent.db)
            query.prepare("UPDATE `reinforcements_groups` SET amount=? WHERE `userId`=? AND `group` = ? AND `unit` = ?")
            query.addBindValue(newAmount)
            query.addBindValue(self.uid)
            query.addBindValue(origin)
            query.addBindValue(itemuid)
            if not query.exec_():
                self.log.warning(query.lastError())
        
        # Then add the amount in the new group
        query = QSqlQuery(self.parent.db)        
        query.prepare("INSERT INTO `reinforcements_groups`(`userId`, `group`, `unit`, `amount` ) VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE `amount` = `amount` + ?")
        query.addBindValue(self.uid)
        query.addBindValue(destination)
        query.addBindValue(itemuid)
        query.addBindValue(amount)
        query.addBindValue(amount)
        if not query.exec_():
            self.log.warning(query.lastError())        
            
        self.send_group_reinforcements_info()
        

    def command_offer_reinforcement_group(self, message):
        '''offer a reinforcement group'''
        to = message["giveTo"]
        unit = message["itemuid"]
        amount = message["amount"]
        price  = 0
        
        if unit == 0:
            # this is a autorecall
            if self.credits >= (AUTORECALL * amount):
                
                query = QSqlQuery(self.parent.db)
                query.prepare("INSERT INTO `item_bought`(`useruid`, `itemuid`, `amount` ) VALUES (?,?,?) ON DUPLICATE KEY UPDATE `amount` = `amount` + ?")
                query.addBindValue(to)
                query.addBindValue(0)
                query.addBindValue(amount)
                query.addBindValue(amount)
                if query.exec_():
                    self.removeCredits(AUTORECALL * amount)
                    for conn in self.parent.recorders:
                        if conn.uid == to:
                            conn.send_reinforcements_items()
                            conn.send_group_reinforcements_info()
                            return            
            return
      
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT tech_level, blueprint FROM faf_unitsDB.vvjnxsdj89235d WHERE bp_name = ? AND tech_level <= (SELECT IF(category = 'Building - Weapon' ,?-1,?))")
        query.addBindValue(unit)
        query.addBindValue(self.rank)
        query.addBindValue(self.rank)
        if not query.exec_():
            self.log.warning(query.lastError())
        
        if query.size()!= 0:
            query.first()
            tech_level = int(query.value(0))
            if tech_level >= 4:
                return            
            blueprint = base64.b64decode(str(query.value(1)))
            bpdecoded = phpserialize.loads(blueprint)                
            mass = int(bpdecoded["UnitBlueprint"]["Economy"]["BuildCostMass"])
            price = self.computeMassCost(mass, tech_level) * amount
            if self.credits >= price :
                # we can add it
                query2 = QSqlQuery(self.parent.db)        
                query2.prepare("INSERT INTO `reinforcements_groups`(`userId`, `group`, `unit`, `amount` ) VALUES (?,0,?,?) ON DUPLICATE KEY UPDATE `amount` = `amount` + ?")
                query2.addBindValue(to)
                query2.addBindValue(unit)
                query2.addBindValue(amount)
                query2.addBindValue(amount)
                if not query2.exec_():
                    self.log.warning(query2.lastError())                    
                else:
                    self.removeCredits(price)                

                for conn in self.parent.recorders:
                    if conn.uid == to:
                        conn.send_reinforcements_items()
                        conn.send_group_reinforcements_info()
                        return
            
        
    def command_buy_reinforcement_group(self, message):
        '''build a reinforcement group'''
        unit = message["itemuid"]
        amount = message["amount"]
        price  = 0
        
        if unit == 0:
            # this is a autorecall
            if self.credits >= (AUTORECALL * amount):
                
                query = QSqlQuery(self.parent.db)
                query.prepare("INSERT INTO `item_bought`(`useruid`, `itemuid`, `amount` ) VALUES (?,?,?) ON DUPLICATE KEY UPDATE `amount` = `amount` + ?")
                query.addBindValue(self.uid)
                query.addBindValue(0)
                query.addBindValue(amount)
                query.addBindValue(amount)
                if query.exec_():
                    self.removeCredits(AUTORECALL * amount)
                    self.send_group_reinforcements_info()
                else:
                    self.log.debug(query.lastError())
         
            return        
        
        
        # we need to compute the price and check if we can afford it
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT tech_level, blueprint FROM faf_unitsDB.vvjnxsdj89235d WHERE bp_name = ? AND tech_level <= (SELECT IF(category = 'Building - Weapon' ,?-1,?))")
        query.addBindValue(unit)
        query.addBindValue(self.rank)
        query.addBindValue(self.rank)
        if not query.exec_():
            self.log.warning(query.lastError())
        
        if query.size()!=0:
            query.first()
            tech_level = int(query.value(0))
            if tech_level >= 4:
                return
            blueprint = base64.b64decode(str(query.value(1)))
            bpdecoded = phpserialize.loads(blueprint)                
            mass = int(bpdecoded["UnitBlueprint"]["Economy"]["BuildCostMass"])
            price = self.computeMassCost(mass, tech_level) * amount
            if self.credits >= price :
                # we can add it
                
                query2 = QSqlQuery(self.parent.db)        
                query2.prepare("INSERT INTO `reinforcements_groups`(`userId`, `group`, `unit`, `amount` ) VALUES (?,0,?,?) ON DUPLICATE KEY UPDATE `amount` = `amount` + ?")
                query2.addBindValue(self.uid)
                query2.addBindValue(unit)
                query2.addBindValue(amount)
                query2.addBindValue(amount)
                if not query2.exec_():
                    self.log.warning(query2.lastError())        
                else:
                    self.removeCredits(price)                
                    self.send_group_reinforcements_info()
                    
        

    def command_buy_building(self, message):
        itemuid     = message["uid"]
        planetuid   = message["planetuid"]
        faction = self.getCombatFaction()
        #check if we control that planet...
        if not self.parent.planets[planetuid][FACTIONS[faction]] > ATTACK_THRESHOLD :
            self.sendJSON(dict(command="notice", style="info", text="You can't build on a planet with less than 51% influence."))
            return       
        
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT price FROM static_defenses WHERE id = ?")
        query.addBindValue(itemuid)
        query.exec_()
        if query.size() > 0:
            query.first()
            cost = int(query.value(0)) 
            if cost > self.credits:
                self.sendJSON(dict(command="notice", style="info", text="You don't have enough credits to buy this item."))
                return
            self.removeCredits(cost)
        else :
            return        

        # buy it..
        query = QSqlQuery(self.parent.db)
        query.prepare("INSERT INTO `planets_defense`(`planetuid`, `itemuid`,`amount`) VALUES (?,?,1) ON DUPLICATE KEY UPDATE amount=amount+1")
        query.addBindValue(planetuid)
        query.addBindValue(itemuid)
        query.exec_()       
        self.parent.planetaryDefenses.update()
        self.parent.sendPlanetDefenseUpdateToAll(planetuid)
        #self.send_temporary_items()

    def command_buy_temporary_item(self, message):
        '''buy an item'''
        itemuid = message["uid"]
        # check that we can buy that..
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT price FROM static_defenses WHERE id = ? and temporary = 1")
        query.addBindValue(itemuid)
        query.exec_()
        if query.size() > 0:
            query.first()
            cost = int(query.value(0)) 
            if cost > self.credits:
                self.sendJSON(dict(command="notice", style="info", text="You don't have enough credits to buy this item."))
                return
            self.removeCredits(cost)
        else :
            return
        
        # buy it..
        query = QSqlQuery(self.parent.db)
        query.prepare("INSERT INTO `item_bought`(`avataruid`, `itemuid`,`amount`) VALUES (?,?,1) ON DUPLICATE KEY UPDATE amount=amount+1")
        query.addBindValue(self.avataruid)
        query.addBindValue(itemuid)
        query.exec_()       
        self.send_temporary_items()

    def command_reinforcements_items(self, message):
        self.send_reinforcements_items()

    def command_temporary_items(self, message):
        self.send_temporary_items()
        
    def command_planetary_defense_items(self, message):
        self.send_building_items()
    
    
    def computeTimeReinforcement(self, mass, tech):
        return math.pow(math.log1p(tech),4.1) * (mass / self.parent.massFactors[self.faction][tech-1])
    
    def computeMassCost(self, mass, tech):
        normPrices = [30, 200, 600] 
        normalizedPrice = normPrices[tech-1]
        massFactor = self.parent.massFactors[self.faction][tech-1]
        self.log.debug(massFactor)
        return int(normalizedPrice * (mass /massFactor ))
        
    
    def send_reinforcements_items(self):
        ''' send what the player can buy'''
        
        dominating = False
        factions = [FACTIONS[self.faction]]
        if self.faction in self.parent.domination.getDominants():
            dominating = True
            for slave in self.parent.domination.getDominantSlaves(self.faction):
                factions.append(FACTIONS[slave])
        
        if self.dominatedBy != None:
            factions.append(FACTIONS[self.dominatedBy])

        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT bp_name, unit_name, unit_type, tech_level, blueprint, LOWER(faction) FROM faf_unitsDB.vvjnxsdj89235d WHERE category = 'Vehicle' and LOWER(faction) in %s and tech_level <= 3" % str(factions).replace("[", "(").replace("]", ")"))
        #query.addBindValue(FACTIONS[self.faction])
        if not query.exec_() :
            self.log.error(query.lastError())
        if query.size() > 0:
            while next(query):
                bp_name = str(query.value(0))
                unit_name = str(query.value(1))
                unit_type = str(query.value(2))
                tech_level = int(query.value(3))
                blueprint = base64.b64decode(str(query.value(4)))
                bpdecoded = phpserialize.loads(blueprint)
                mass = int(bpdecoded["UnitBlueprint"]["Economy"]["BuildCostMass"])
                price = self.computeMassCost(mass, tech_level)
                delay = self.computeTimeReinforcement(mass, tech_level)
                
                display=True
                if tech_level > self.rank:
                    display=False
                
                if self.dominatedBy != None and str(query.value(5)) != FACTIONS[self.faction]:
                    display=False
                
             
                item = dict(command="reinforcement_item_info", type="unit", display=display, uid=bp_name, name=unit_name, tech = tech_level, price=price, activation=delay, description=unit_type)
                self.sendJSON(item)
            
        # and the building reinforcements...
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT bp_name, unit_name, unit_type, tech_level, blueprint, LOWER(faction) FROM faf_unitsDB.vvjnxsdj89235d WHERE category = 'Building - Weapon' and LOWER(faction) in %s and tech_level <= 3" % str(factions).replace("[", "(").replace("]", ")"))
        #query.addBindValue(FACTIONS[self.faction])
        if not query.exec_() :
            self.log.error(query.lastError())
        if query.size() > 0:
            while next(query):
                bp_name = str(query.value(0))
                unit_name = str(query.value(1))
                unit_type = str(query.value(2))
                tech_level = int(query.value(3))
                blueprint = base64.b64decode(str(query.value(4)))
                bpdecoded = phpserialize.loads(blueprint)
                mass = int(bpdecoded["UnitBlueprint"]["Economy"]["BuildCostMass"])
                price = self.computeMassCost(mass, tech_level)
                delay = self.computeTimeReinforcement(mass, tech_level)
                
                display=True
                if tech_level+1 > self.rank:
                    display=False
                
                if self.dominatedBy != None and str(query.value(5)) != FACTIONS[self.faction]:
                    display=False
                
#                if dominating == True and str(query.value(5)) != FACTIONS[self.faction]:
#                    display=False 
                
                item = dict(command="reinforcement_item_info", type="building", display=display, uid=bp_name, name=unit_name, tech = tech_level, price=price, activation=delay, description=unit_type)
                self.sendJSON(item)
        
        
        # now the passive items
        item = dict(command="reinforcement_item_info", type="active", display=True, uid=0, name="Auto Recall", tech = 0, price=500, activation=0, description="Recall automatically if your ACU health is 0.")
        self.sendJSON(item)
        # now we send the current reinforcements for the player.
        self.send_group_reinforcements_info()
    
    def send_group_reinforcements_info(self):
        '''send the current reinforcements for the player.'''
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT `group` , `unit` , `amount` FROM `reinforcements_groups` WHERE `userId` = ?")
        query.addBindValue(self.uid)
        query.exec_()
        if query.size() > 0:
            while next(query):
                group = int(query.value(0))
                unit = str(query.value(1))
                amount = int(query.value(2))
                item = dict(command="group_reinforcements_info", group=group, unit=unit, amount = amount)
                self.sendJSON(item)
             
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT `itemuid`, `amount` FROM `item_bought` WHERE `useruid` = ?")
        query.addBindValue(self.uid)
        query.exec_()
        if query.size() > 0:
            while next(query):
                unit = int(query.value(0))
                amount = int(query.value(1))
                item = dict(command="group_reinforcements_info", group=0, unit=unit, amount = amount)
                self.sendJSON(item)        

    def send_building_items(self):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT id, structure, price, activation, description FROM static_defenses WHERE faction = ? and rank <= ?")
        query.addBindValue(self.faction)
        query.addBindValue(self.rank)
        self.log.debug(self.faction)
        self.log.debug(self.rank)
        if not query.exec_() :
            self.log.error(query.lastError())
        if query.size() > 0:
            while next(query):
                itemuid = int(query.value(0))
                item = dict(command="planetary_defense_info", static=True, uid=itemuid, structure=str(query.value(1)), price=int(query.value(2)), activation=int(query.value(3)), description=str(query.value(4)))
                self.sendJSON(item)
    
    def send_temporary_items(self):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT id, structure, price, activation, description FROM static_defenses WHERE faction = ? and rank <= ? and temporary = 1")
        query.addBindValue(self.faction)
        query.addBindValue(self.rank)
        self.log.debug(self.faction)
        self.log.debug(self.rank)
        if not query.exec_() :
            self.log.error(query.lastError())
        if query.size() > 0:
            while next(query):
                itemuid = int(query.value(0))
                query2 = QSqlQuery(self.parent.db)
                amount = 0
                query2.prepare("SELECT amount FROM item_bought WHERE avataruid = ? AND itemuid = ?")
                query2.addBindValue(self.avataruid)
                query2.addBindValue(itemuid)
                if not query2.exec_() :
                    self.log.error(query2.lastError())
                if query2.size() >0:
                    query2.first()
                    amount = int(query2.value(0))
                item = dict(command="reinforcement_info", amount = amount, static=True, temporary=True, uid=itemuid, structure=str(query.value(1)), price=int(query.value(2)), activation=int(query.value(3)), description=str(query.value(4)))
                self.sendJSON(item)


    def command_ranking_up(self, message):
        ''' Handling ranking up '''
        if self.rank == 7 :
            self.sendJSON(dict(command="notice", style="info", text="You are already the highest ranked player in your faction."))
            return

        if self.rank == 6 :
            #we must check that there is only one "tip of the spear"
            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT `rank` FROM `avatars` LEFT JOIN accounts ON accounts.uid =  avatars.uid WHERE faction = ? AND rank = 7 and alive = 1")
            query.addBindValue(self.faction)
            query.exec_()
            if query.size() > 0 :
                self.sendJSON(dict(command="notice", style="info", text="Someone else is already the tip of the spear."))
                return
            
        rankRequisite = ranksRequirement[self.rank+1]
        
        self.log.debug("ranking up from %i to %i requires %i money" % (self.rank, self.rank+1, rankRequisite["money"]))
        
        if self.credits < rankRequisite["money"] or self.victories < rankRequisite["victories"] :
                self.sendJSON(dict(command="notice", style="info", text="You need %i credits and %i victories to rank up." % (rankRequisite["money"], rankRequisite["victories"])))
                return
        
        # if we are here, we can rank up...
        
        
        query = QSqlQuery(self.parent.db)
        query.prepare("UPDATE `avatars` SET rank=rank+1 WHERE uid = ? and alive = 1")
        query.addBindValue(self.uid)
        if not query.exec_() :
            self.log.error(query.lastError())
            return

        

        # we update the player list ranks...
        if self.uid in self.parent.factionPlayers[self.faction][self.rank] : 
            self.parent.factionPlayers[self.faction][self.rank].remove(self.uid)
        
        self.parent.factionPlayers[self.faction][self.rank+1].append(self.uid)
        
        # and finally we send the new rank to the player.
        self.removeCredits(rankRequisite["money"])
        
        self.parent.newsFeed.rankingUp(self.uid, self.faction)

    def command_send_to_proposal(self, message):
        planetuid = message["uid"]

        if not planetuid in self.parent.attacks.cleanGames(self.uid):
            return
      
        if self.parent.attacks.checkAttackNumber(self.uid, -1) :
                self.sendJSON(dict(command="notice", style="info", text="You can't give multiple attacks at once."))
                return

        self.parent.attackOnHold[planetuid] = time.time()
       
        self.log.debug("setting attack on planet %i on hold" % planetuid)
        self.parent.attacks.setOnHold(planetuid)
        
        #cleaning teams and stuff
        self.parent.attacks.removeAttackers(planetuid)
        self.parent.attacks.removeDefenders(planetuid)
        
        #adding back attacker for faction.
        self.parent.attacks.addAttacker(planetuid, self.uid, self.getCombatFaction())
        
        if planetuid in self.parent.defendersOnHold :
            del self.parent.defendersOnHold[planetuid]

        self.parent.updateAttackList()
        self.parent.sendAttackToAll()     
        

    def checkSquad(self, planetuid):
        if self.parent.teams.isInSquad(self.uid):
            if self.parent.teams.isLeader(self.uid) == False:
                self.sendJSON(dict(command="notice", style="info", text="Only the squad leader can order an attack or a defense."))
                return False
            else:
                members = self.parent.teams.getAllMembers(self.uid)
                # check the map spawn.
                sizeSquad = len(members)
                
                planetSize = self.planetMaxSize(planetuid)
                if sizeSquad > planetSize:
                    self.sendJSON(dict(command="notice", style="info", text= ("The planet is too small for your squad size. Max size : " + str(planetSize))))
                    return False
                # check all squad member
                
                for conn in self.parent.recorders:
                    if conn.uid in members:
                        if conn.inBattle :                            
                            self.sendJSON(dict(command="notice", style="info", text= (conn.user["login"] + " is already in battle !")))
                            return False
                        if conn.away == True :
                            self.sendJSON(dict(command="notice", style="info", text=(conn.user["login"] + " is not available for battle ! (away)")))
                            return False
        return True


    def planetMaxSize(self, planetuid):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT FLOOR(max_players/2) FROM planet_maps LEFT JOIN faf_lobby.table_map ON faf_lobby.table_map.id = planet_maps.mapuid WHERE planetuid = ?")
        query.addBindValue(planetuid)
        query.exec_()    
        if query.size > 0:
            query.first()
            return int(query.value(0))
        return 0

    def command_defense_command(self, message):
        '''handling planetary defense'''
        
        faction = self.getCombatFaction()
        if faction == None:
            return
        planetuid = int(message["uid"])

        if self.parent.attacks.isDefended(planetuid):
            return
        
        defendersuid = self.parent.attacks.getTeamUids(planetuid, 2)
        for uid in defendersuid :
            self.log.debug(uid)
        
        if not self.checkSquad(planetuid):
            return

        if self.inBattle == True :
            self.log.debug("player %i in battle." % self.uid)
            self.sendJSON(dict(command="notice", style="info", text="You can't defend while you are in battle !"))
            return

        if self.away == True :
            self.sendJSON(dict(command="notice", style="info", text="You can't defend if you are not available for battle !"))
            return         
        
        if self.parent.attacks.isOnHold(planetuid):
            return
        
        self.parent.updateGalaxy()
        
        if not self.parent.planets[planetuid][FACTIONS[faction]] > ATTACK_THRESHOLD :
            self.sendJSON(dict(command="notice", style="info", text="You can't defend a planet with less than 51% influence."))
            return
        
        canDefend   = False
        
#        if self.parent.attacks.isTeamFull(planetuid, 2) :
#            self.log.debug("Team is full %i" % planetuid)
#            self.sendJSON(dict(command="notice", style="info", text="This planet is defended."))
#            return
        
        if self.parent.attacks.isDefended(planetuid) or (planetuid in self.parent.defendersOnHold) :
            if planetuid in self.parent.defendersOnHold :
                self.log.debug("there is a defenser on hold for planet %i" % planetuid)
                
                for rank in self.parent.factionPlayers[faction] :
                    self.log.debug("Checking rank %i" % rank)
                    for uid in self.parent.defendersOnHold[planetuid] :
                        if uid in self.parent.factionPlayers[faction][rank] :
                            self.log.debug("Defender on Hold  for planet %i user %i" % (planetuid, uid))
                            self.sendJSON(dict(command="notice", style="info", text="This planet will be defended soon already !"))
                            return      
                    
                del self.parent.defendersOnHold[planetuid]      

            else :
                self.log.debug("Planet %i already defended" % planetuid)
                self.sendJSON(dict(command="notice", style="info", text="This planet is currently defended !"))
                return        
            

        if self.parent.attacks.getFirstFaction(planetuid) != faction :
            for site in self.getLinkedPlanets(planetuid) :
                if self.parent.planets[site][FACTIONS[faction]] > ATTACK_THRESHOLD :
                    canDefend   = True
                    break            

        else :
            
            defenseToDelete = []
            for uid in self.parent.defendersOnHold :
                if self.parent.defendersOnHold[uid] == self.uid :
                    defenseToDelete.append(uid)
                    
            for uid in defenseToDelete :
                del self.parent.defendersOnHold[uid] 
            
            self.sendJSON(dict(command="notice", style="info", text="You can't defend a planet attacked by your own faction !"))
            return

        
        if canDefend :
            self.sendJSON(dict(command="searching", state="on", text="searching for attackers..."))
            self.log.debug("adding defenser %i to planet %i" % (self.uid, planetuid))
            
            
            self.parent.attacks.addDefenser(planetuid, self.uid, faction)
            
            if self.parent.teams.isInSquad(self.uid):
                #we add all other squad members
                for memberid in self.parent.teams.getAllMembers(self.parent.teams.getSquadLeader(self.uid)):
                    if self.uid != memberid:
                        self.parent.attacks.addDefenser(planetuid, memberid, faction)
                        for conn in self.parent.recorders:
                            if conn.uid == memberid:
                                self.inBattle = True
                
            self.parent.tryLaunchGame(planetuid)
            self.inBattle = True
        

    def command_attack_command(self, message):
        '''Handling player attack '''

        faction = self.getCombatFaction()
        if faction == None:
            return
        
        planetuid = int(message["uid"])
        if not self.checkSquad(planetuid):
            return

        if self.parent.attacks.isDefended(planetuid) or (planetuid in self.parent.defendersOnHold) :
            if planetuid in self.parent.defendersOnHold :
                self.log.debug("there is a defenser on hold for planet %i" % planetuid)
                
                for rank in self.parent.factionPlayers[faction] :
                    self.log.debug("Checking rank %i" % rank)
                    for uid in self.parent.defendersOnHold[planetuid] :
                        if uid in self.parent.factionPlayers[faction][rank] :
                            self.log.debug("Defender on Hold  for planet %i user %i" % (planetuid, uid))
                            self.sendJSON(dict(command="notice", style="info", text="This planet will be defended soon already !"))
                            return      
                    
                del self.parent.defendersOnHold[planetuid]      

            else :
                self.log.debug("Planet %i already defended" % planetuid)
                self.sendJSON(dict(command="notice", style="info", text="This planet is currently defended !"))
                return      

        if self.inBattle == True :
            self.log.debug("player %i in battle." % self.uid)
            self.sendJSON(dict(command="notice", style="info", text="You can't attack while you are in battle!"))
            return        

        if self.away == True :
            self.sendJSON(dict(command="notice", style="info", text="You can't attack if you are not available for battle!"))
            return  

        if self.parent.attacks.isOnHold(planetuid):
            self.log.debug("attackForPlayer:" +str(self.parent.attacks.getAttackFrom(self.uid)))
            if planetuid in self.parent.attacks.getAttackFrom(self.uid):
                if self.parent.attacks.checkAttackNumber(self.uid, -1) :
                    self.sendJSON(dict(command="notice", style="info", text="You can't attack more than one planet."))
                    return
            else:
                if self.parent.attacks.checkAttackNumber(self.uid) :
                    self.sendJSON(dict(command="notice", style="info", text="You can't attack more than one planet."))
                    return
                                        
        elif self.parent.attacks.checkAttackNumber(self.uid) :
                self.sendJSON(dict(command="notice", style="info", text="You can't attack more than one planet at once."))
                return

        self.parent.updateGalaxy()
  
        if self.parent.planets[planetuid][FACTIONS[faction]] > CONTROL_THRESHOLD :
            self.sendJSON(dict(command="notice", style="info", text="This planet is already under your faction control."))
            return

        canAttack = False
        for site in self.getLinkedPlanets(planetuid) :
            if self.parent.planets[site][FACTIONS[faction]] >= ATTACK_THRESHOLD :
                canAttack = True
                break

        if canAttack :
            if self.parent.attacks.isOnHold(planetuid):
                if self.parent.attacks.getFirstFaction(planetuid) == faction:
                    self.log.debug("giving the attack on planet %i to %i" % (planetuid, self.uid))
                    for attackuid in self.parent.attacks.attacks:
                        if self.parent.attacks.attacks[attackuid].getPlanet() == planetuid : 
                            self.parent.attacks.attacks[attackuid].team1 = {}
                            break
                    self.parent.attacks.resetState(planetuid)
                    query = QSqlQuery(self.db)
                    query.prepare("UPDATE `attacks` SET `uid_player`= ?, attack_time = NOW() WHERE `uid_planet` = ?")
                    query.addBindValue(self.uid)
                    query.addBindValue(planetuid)
                    if not query.exec_() :
                        self.log.debug(query.lastError())
                    else:
                        self.parent.updateAttackList()
                        self.addTeamAttack(planetuid)
                        self.parent.sendAttackToAll() 
                        if planetuid in self.parent.attackOnHold:
                            del self.parent.attackOnHold[planetuid]
                return

            self.updateCredits()
            finalCost = COST_ATTACK * self.rank
            if self.credits < finalCost :
                self.sendJSON(dict(command="notice", style="info", text="You don't have enough credits. (%i required)" % finalCost))
                return
            
            if self.parent.attacks.isUnderAttack(planetuid) :
                if self.parent.attacks.getFirstFaction(planetuid) == faction :
                    self.sendJSON(dict(command="notice", style="info", text="Your faction is already attacking this planet."))
                    return
                else :
#                    if self.parent.attacks.isTeamFull(planetuid, 2) :
#                        self.sendJSON(dict(command="notice", style="info", text="Your faction is already attacking this planet, and the team is full"))
#                        return              
                    self.sendJSON(dict(command="searching", state="on", text="searching for the other attackers..."))
                    self.parent.attacks.addDefenser(planetuid, self.uid, faction)
                    if self.parent.teams.isInSquad(self.uid):
                        #we add all other squad members
                        for memberid in self.parent.teams.getAllMembers(self.parent.teams.getSquadLeader(self.uid)):
                            if self.uid != memberid:
                                self.parent.attacks.addDefenser(planetuid, memberid, faction)
                                for conn in self.parent.recorders:
                                    if conn.uid == memberid:
                                        self.inBattle = True                    
                    
                    self.parent.attacks.setMutualAttack(planetuid)
                    self.log.debug("this is a mutual attack on planet %i for user %i" % (planetuid, self.uid))
                    self.parent.tryLaunchGame(planetuid)
                    self.inBattle = True
        
            # Checking if the guy has enough money !
            if finalCost > 0:
                self.credits = self.credits - finalCost
                self.removeCredits(finalCost)
            if self.parent.attacks.isMutualAttack(planetuid) == False :
                self.log.debug("this is not a mutual attack - registering the attack on planet %i for user %i" % (planetuid, self.uid))
                self.updateAttackList(planetuid)
                self.addTeamAttack(planetuid)

        else :
            self.sendJSON(dict(command="notice", style="info", text="You can't attack this planet."))        


    def addTeamAttack(self, planetuid): 
        self.log.debug("checking team")
        if self.parent.teams.isInSquad(self.uid):
            #we add all other squad members
            for memberid in self.parent.teams.getAllMembers(self.parent.teams.getSquadLeader(self.uid)):
                if self.uid != memberid:
                    self.log.debug("adding attacker %i for planet %i" % (memberid, planetuid))
                    self.parent.attacks.addAttacker(planetuid, memberid, self.getCombatFaction())


    def command_away(self, message):
        state = message["state"]
        if state == 1 :
            self.log.debug("player %i is marked away" % self.uid)
            self.away = True
            self.parent.cleanGames(self.uid)
        else :
            self.log.debug("player %i is back from away" % self.uid)
            self.away = False


    def getLinkedPlanets(self, planet):
        planets = []
        if planet in self.parent.links : 
            planets = copy.deepcopy(self.parent.links[planet])  
        for link in self.parent.links :
            if link != planet :
                if planet in self.parent.links[link] :
                    planets.append(link)
        return planets   
                

    def command_request(self, message):
        action = message["action"]
        if action == "shaders" :
            self.sendJSON(dict(command="shader", name = "swirl", shader_fragment=STARS_FRAGMENT_SRC, shader_vertex=SWIRL_VERTEX_SRC))
            self.sendJSON(dict(command="shader", name = "constant", shader_fragment=CONSTANT_FRAGMENT_SRC, shader_vertex=CONSTANT_VERTEX_SRC))
            self.sendJSON(dict(command="shader", name = "planet", shader_fragment=PLANET_FRAGMENT_SRC, shader_vertex=PLANET_VERTEX_SRC))          
            self.sendJSON(dict(command="shader", name = "atmosphere", shader_fragment=ATMOSPHERE_FRAGMENT_SRC, shader_vertex=ATMOSPHERE_VERTEX_SRC))           
            self.sendJSON(dict(command="shader", name = "selection", shader_fragment=ATMOSPHERE_FRAGMENT_SRC, shader_vertex=SELECTION_VERTEX_SRC))
            self.sendJSON(dict(command="shader", name = "stars", shader_fragment=STARS_FRAGMENT_SRC, shader_vertex=STARS_VERTEX_SRC))            
            self.sendJSON(dict(command="shader", name = "background", shader_fragment=BACK_FRAGMENT_SRC, shader_vertex=STARS_VERTEX_SRC))            



   
    def command_init_done(self, message):

        if message['status'] == True :
            
            self.sendDefenses(True)
            self.sendDepots()
            ## checking if the current user has a faction...
            query = QSqlQuery(self.parent.db)
            query.prepare("SELECT faction FROM `accounts` WHERE uid = ?")
            query.addBindValue(self.uid)
            query.exec_()
            if query.size() == 1 :
                query.first()
                self.faction = int(query.value(0))
                if self.get_name() :
                    self.loggedIn()
                
            else :
                if self.uid != None:
                    self.sendJSON(dict(command="create_account", action = 0))
                else:
                    self.socket.abort()
                         
    def command_account_creation(self, message):
        action = message["action"]
        if action == 0 : 
            faction = message["faction"]
            query = QSqlQuery(self.parent.db)
            query.prepare("INSERT INTO `accounts` (uid, faction) VALUES (?,?) ON DUPLICATE KEY UPDATE faction = ?")
            query.addBindValue(self.uid)
            query.addBindValue(faction)
            query.addBindValue(faction)
            
            query.exec_()
            self.faction = faction
            self.get_name()
        
        elif action == 1 :
            self.get_name()
        
        elif action == 2 :
            query = QSqlQuery(self.parent.db)
            query.prepare("INSERT INTO `avatars` (uid, name, rank, victories, credits, alive) VALUES (?, ?, 0, 0, ?, 1)")
            self.credits = INITIAL_CREDITS
            query.addBindValue(self.uid)
            query.addBindValue(self.name)
            query.addBindValue(self.credits)
            query.exec_()
            self.log.debug(query.lastQuery())
            
            self.parent.newsFeed.newPlayer(self.uid, self.faction)
            
            if not self.logged :
                self.loggedIn()
            else :
                if not self.uid in self.parent.factionPlayers[self.faction][self.rank] : 
                    self.parent.factionPlayers[self.faction][self.rank].append(self.uid)                
                self.updatePlayerStats()
                   

    def get_session(self, login):
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT id, session FROM faf_lobby.login WHERE login = ?")
        query.addBindValue(login)
        query.exec_()
        if query.size() > 0:
            query.first()
            uid = int(query.value(0))
            session = int(query.value(1))
            self.parent.parent.listUsers[uid] = dict(login=login, uid=uid, session=session)
            
            return uid
        return None
        

    def command_hello(self, message):
        login = message["login"]
        session = message["session"]
        version = message["version"]
        
        self.uid = self.get_session(login)
        
        if not "port" in message :
            port = 6112
        else:
            port = int(message["port"])

        if self.uid in self.parent.parent.listUsers :
            user = self.parent.parent.listUsers[self.uid]
            if user["login"] == login : 
                if str(user["session"]) == str(session) :
                    self.user = user
                    


#                    if version != "development" :
#                        self.sendJSON(dict(command="notice", style="info", text="Galactic War will come back soon with a big surprise..."))
#                        return

                    query = QSqlQuery(self.parent.db)
                    query.prepare("SELECT version, file FROM version_lobby WHERE version = ( SELECT MAX( version ) FROM version_lobby )")
                    query.exec_()
                    if  query.size() == 1:
                        query.first()
                        versionDB = int(query.value(0))
                        f = query.value(1)
                        if version != "development" :
                            if int(version.split(".")[-1]) < versionDB   :
                                self.log.debug("sending update")
                                self.sendJSON(dict(command="update", update=f))
                                return                 
                    
                    self.parent.parent.send(dict(command="settings", port=port, uid=int(self.uid)))
                    self.sendPlanets()
                    self.sendJSON(dict(command="welcome"))

                    self.sendJSON(dict(command="resource_required", action="shaders", data = ["constant", "planet", "atmosphere", "stars",  "background"] ))                       
                    self.sendJSON(dict(command="resource_required", action="textures", data = dict(depot =self.getMd5(os.path.join(TEXPATH, "depot.png")), attack = self.getMd5(os.path.join(TEXPATH, "attack.png")),background = self.getMd5(os.path.join(TEXPATH, "background.png")), star=self.getMd5(os.path.join(TEXPATH, "star.png"))) ))

                    for conn in self.parent.recorders:
                        
                        if conn.uid == int(self.uid) and conn != self:
                            self.log.debug("closing connection %i" % self.uid)
                            conn.socket.abort()
                            conn.uid = None
                    
                    self.sendEndInit()
                    return
        
        else:
            self.sendJSON(dict(command="notice", style="error", text="You are not connected to FAF server."))
        
    def updatePlayerStats(self):
        
        query = QSqlQuery(self.parent.db)
        query.prepare("SELECT * FROM `avatars` WHERE uid = ? AND alive = 1")
        query.addBindValue(self.uid)
        query.exec_()
        if query.size() == 1 :
            query.first()
            self.avataruid  = int(query.value(7))
            if not self.avataruid:
                return 
            self.log.debug("avatar: %i" % self.avataruid )
            self.name       = str(query.value(1)) 
            self.rank       = int(query.value(2))
            self.victories  = int(query.value(3))
            self.credits    = int(query.value(4))
        
        if self.faction != None :
            self.log.debug("sending player stats %i" % self.uid)
            self.sendJSON(dict(command="player_info", uid = self.uid, name = self.name, faction = self.faction, rank = self.rank, victories = self.victories, credits = self.credits))


    def command_ask_session(self, message):
        jsonToSend = {}
        jsonToSend["command"] = "welcome"
        jsonToSend["session"] = self.session
        self.sendJSON(jsonToSend)   

    def readDatas(self):
        try :
            if self.socket.bytesAvailable() == 0 :
                return       
            ins = QtCore.QDataStream(self.socket)
            ins.setVersion(QtCore.QDataStream.Qt_4_2)       
            while ins.atEnd() == False :
                if self.blockSize == 0:
                    if self.socket.bytesAvailable() < 4:
                        return
                    self.blockSize = ins.readUInt32()
                if self.socket.bytesAvailable() < self.blockSize:
                    #bytesReceived = str(self.socket.bytesAvailable())
                    return
                #bytesReceived = str(self.socket.bytesAvailable())
                action = ins.readQString()
                self.handleAction(action, ins)
                self.blockSize = 0
        except :
            self.log.exception("Something awful happened in a gw thread !")

    def handleAction(self, action, stream):
        if action == "PONG" :
            self.ponged = True
        else :
            self.receiveJSON(action, stream)
        
    def sendArray(self, array):
        if self in self.parent.recorders :
            if self.socket.bytesToWrite() > 16 * 1024 * 1024 :
                self.log.debug("too many to write already")
                return         
            self.socket.write(array)
                  
    def sendJSON(self, data_dictionary):
        '''
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        '''
        data_string = ""
        try :           
            data_string = json.dumps(data_dictionary)
        except :
            return
        self.sendReply(data_string)

    def preparePacket(self, action, *args, **kwargs) :
        reply = QtCore.QByteArray()
        stream = QtCore.QDataStream(reply, QtCore.QIODevice.WriteOnly)
        stream.setVersion(QtCore.QDataStream.Qt_4_2)
        stream.writeUInt32(0)
        stream.writeQString(action)
        for arg in args :
            if type(arg) is LongType :
                stream.writeQString(str(arg))
            elif type(arg) is IntType:
                stream.writeInt(arg)
            elif isinstance(arg, str):                       
                stream.writeQString(arg)                  
            elif type(arg) is StringType  :
                stream.writeQString(arg)
            elif type(arg) is FloatType:
                stream.writeFloat(arg)
            elif type(arg) is ListType:
                stream.writeQString(str(arg))
        stream.device().seek(0)
        stream.writeUInt32(reply.size() - 4)  
        return reply    

    def prepareBigJSON(self, data_dictionary):
        '''
        Simply dumps a dictionary into a string and feeds it into the QTCPSocket
        '''
        data_string = ""
        try :            
            data_string = json.dumps(data_dictionary)
        except :
            return
        return self.preparePacket(data_string)
    
    def receiveJSON(self, data_string, stream):
        '''
        A fairly pythonic way to process received strings as JSON messages.
        '''
        message = json.loads(data_string)
        cmd = "command_" + message['command']
        if hasattr(self, cmd):
            getattr(self, cmd)(message)  
        else:
            self.log.error("command unknown : %s", cmd)
    

    def sendReply(self, action, *args, **kwargs) :
        if self in self.parent.recorders :
            if self.socket.bytesToWrite() > 16 * 1024 * 1024 :
                self.log.error("too many to write already")
                return 
            reply = QtCore.QByteArray()
            stream = QtCore.QDataStream(reply, QtCore.QIODevice.WriteOnly)
            stream.setVersion(QtCore.QDataStream.Qt_4_2)
            stream.writeUInt32(0)
            stream.writeQString(action)
            for arg in args :
                if type(arg) is LongType :
                    stream.writeQString(str(arg))
                elif type(arg) is IntType:
                    stream.writeInt(arg)
                elif isinstance(arg, str):                       
                    stream.writeQString(arg)                  
                elif type(arg) is StringType  :
                    stream.writeQString(arg)
                elif type(arg) is FloatType:
                    stream.writeFloat(arg)
                elif type(arg) is ListType:
                    stream.writeQString(str(arg))
            stream.device().seek(0)         
            stream.writeUInt32(reply.size() - 4)
            if self.socket.write(reply) == -1 :
                self.noSocket = True

    def disconnection(self):
        self.log.debug("disconnection")
        if self.uid != None :
            self.log.debug("player %i disconnected" % self.uid)
            self.command_quit_squad(dict())
            self.parent.cleanGames(self.uid)
            
            
            if self.uid in self.parent.parent.listUsers : 
                del self.parent.parent.listUsers[self.uid]
                
            if self.faction in self.parent.factionPlayers:
                if self.rank in self.parent.factionPlayers[self.faction]:
                    if self.uid in self.parent.factionPlayers[self.faction][self.rank] : 
                        self.parent.factionPlayers[self.faction][self.rank].remove(self.uid)
            
            defToDelete = []
            for uid in self.parent.defendersOnHold :
                if self.uid == self.parent.defendersOnHold[uid] :
                    defToDelete.append(uid)
            for uid in defToDelete :
                del self.parent.defendersOnHold[uid]

            
            
        self.done()
        
    def done(self):
        self.log.debug("we are done")
        try:
            if self.pingTimer != None :
                self.pingTimer.stop()
            if self in self.parent.recorders :
                self.parent.removeRecorder(self)
            if self.socket:
                self.socket.deleteLater()
        except:
            self.log.exception("Something awful happened in a gw thread !")
    def displayError(self, socketError):
        if socketError == QtNetwork.QAbstractSocket.RemoteHostClosedError:
            if not self.uid :
                self.log.warning("RemoteHostClosedError")
            else :
                self.log.warning("RemoteHostClosedError %i" % self.uid)
        elif socketError == QtNetwork.QAbstractSocket.HostNotFoundError:
            if not self.uid :
                self.log.warning("HostNotFoundError")
            else :
                self.log.warning("HostNotFoundError %i" % self.uid)
        elif socketError == QtNetwork.QAbstractSocket.ConnectionRefusedError:
            self.log.warning("ConnectionRefusedError")
        else:
            self.log.warning("The following Error occurred: %s." % self.socket.errorString())

