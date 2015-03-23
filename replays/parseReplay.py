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


'''
Format of command stream:
//
// repeat {
//   uint8 - message typecode (ECmdStreamOp)
//   uint16 - length of message (including header)
//   ... - op specific data
// }
//
enum ECmdStreamOp
{

0    CMDST_Advance,
    // uint32 - number of beats to advance.

1    CMDST_SetCommandSource,
    // uint8 - command source

2    CMDST_CommandSourceTerminated,
    // no args.

3    CMDST_VerifyChecksum,
    // MD5Digest - checksum
    // uint32 - beat number

4    CMDST_RequestPause,
5    CMDST_Resume,
6    CMDST_SingleStep,
    // All with no additional data.

7    CMDST_CreateUnit,
    // uint8 - army index
    // string - blueprint ID
    // float - x
    // float - z
    // float - heading

8    CMDST_CreateProp,
    // string - blueprint ID
    // Vector3f - location

9   CMDST_DestroyEntity,
    // EntId - entity

10    CMDST_WarpEntity,
    // EntId - entity
    // VTransform - new transform
    
11    CMDST_ProcessInfoPair,
    // EntId - entity
    // string - arg1
    // string - arg2

12    CMDST_IssueCommand,
    // uint32 - num units
    // EntIdSet - units
    // CmdData - command data
    // uint8 - clear queue flag

13    CMDST_IssueFactoryCommand,
    // uint32 - num factories
    // EntIdSet - factories
    // CmdData - command data
    // uint8 - clear queue flag

14    CMDST_IncreaseCommandCount,
    // CmdId - command id
    // int32 - count delta

15    CMDST_DecreaseCommandCount,
    // CmdId - command id
    // int32 - count delta

16    CMDST_SetCommandTarget,
    // CmdId - command id
    // STITarget - target

17    CMDST_SetCommandType,
    // CmdId - command id
    // EUnitCommandType - type


18    CMDST_SetCommandCells,
    // CmdId - command id
    // ListOfCells - list of cells
    // Vector3f - pos

19    CMDST_RemoveCommandFromQueue,
    // CmdId - command id
    // EntId - unit

20    CMDST_DebugCommand,
    // string -- the debug command string
    // Vector3f -- mouse pos (in world coords)
    // uint8 -- focus army index
    // EntIdSet -- selection

21    CMDST_ExecuteLuaInSim,
    // string -- the lua string to evaluate in the sim state

22    CMDST_LuaSimCallback,
    // string - callback function name
    // LuaObject - table of function arguments

21    CMDST_EndGame,
    // no args.
};


// Format of EntIdSet:
//
// uint32 - number of entity ids
// repeat number of entity ids times {
//   EndId - entity id
// }


// Format of CmdData:
//
// CmdId - id
// uint8 - command type (EUnitCommandType)
// STITarget - target
// int32 - formation index or -1
// if formation index != -1
// {
//   Quaternionf - formation orientation
//   float - formation scale
// }
// string - blueprint ID or the empty string for no blueprint
// ListOfCells - cells
// int32 - count


// Format of STITarget:
// 
// uint8 - target type (ESTITargetType)
// if target type == STITARGET_Entity {
//   EntId - entity id
// }
// if target type == STITARGET_Position {
//   Vector3f - position
// }


// Format of ListOfCells:
//
// uint32 - num cells
// repeat num cells times {
//   int16 - x
//   int16 - z
// }
'''

class UNITCOMMAND(object):
    UNITCOMMAND_None = 0
    UNITCOMMAND_Stop = 1
    UNITCOMMAND_Move = 2
    UNITCOMMAND_Dive = 3
    UNITCOMMAND_FormMove = 4
    UNITCOMMAND_BuildSiloTactical =5
    UNITCOMMAND_BuildSiloNuke =6
    UNITCOMMAND_BuildFactory =7
    UNITCOMMAND_BuildMobile =8
    UNITCOMMAND_BuildAssist =9
    UNITCOMMAND_Attack =10
    UNITCOMMAND_FormAttack =11
    UNITCOMMAND_Nuke =12
    UNITCOMMAND_Tactical =13
    UNITCOMMAND_Teleport =14
    UNITCOMMAND_Guard =15
    UNITCOMMAND_Patrol =16
    UNITCOMMAND_Ferry =17
    UNITCOMMAND_FormPatrol =18
    UNITCOMMAND_Reclaim =19
    UNITCOMMAND_Repair =20
    UNITCOMMAND_Capture =21
    UNITCOMMAND_TransportLoadUnits =22
    UNITCOMMAND_TransportReverseLoadUnits =23
    UNITCOMMAND_TransportUnloadUnits =24
    UNITCOMMAND_TransportUnloadSpecificUnits =25
    UNITCOMMAND_DetachFromTransport =26
    UNITCOMMAND_Upgrade =27
    UNITCOMMAND_Script =28
    UNITCOMMAND_AssistCommander =29
    UNITCOMMAND_KillSelf =30
    UNITCOMMAND_DestroySelf =31
    UNITCOMMAND_Sacrifice =32
    UNITCOMMAND_Pause =33
    UNITCOMMAND_OverCharge =34
    UNITCOMMAND_AggressiveMove =35
    UNITCOMMAND_FormAggressiveMove =36
    UNITCOMMAND_AssistMove =37
    UNITCOMMAND_SpecialAction =38
    UNITCOMMAND_Dock =39


'''
// Format of CmdData: 
// 
// CmdId - id 
// uint8 - command type (EUnitCommandType) 
// STITarget - target 
// int32 - formation index or -1 
// if formation index != -1 
// { 
//   Quaternionf - formation orientation 
//   float - formation scale 
// } 
// string - blueprint ID or the empty string for no blueprint 
// ListOfCells - cells 
// int32 - count 

// Format of STITarget: 
// 
// uint8 - target type (ESTITargetType) 
// if target type == STITARGET_Entity { 
//   EntId - entity id 
// } 
// if target type == STITARGET_Position { 
//   Vector3f - position 
// } 


// Format of ListOfCells: 
// 
// uint32 - num cells 
// repeat num cells times { 
//   int16 - x 
//   int16 - z 
// } 

// Format of EntIdSet: 
// 
// uint32 - number of entity ids this may be gone
// repeat number of entity ids times { 
//   EndId - entity id 
// }'''

import struct
import json

from PyQt4 import QtCore

from .ReplayArmy import *
from .replayArmyContainer import *
from .replayInfos import *

TYPE_NUMBER = 0
TYPE_STRING = 1
TYPE_NIL = 2
TYPE_BOOLEAN = 3
TABLE_BEGIN = 4
TABLE_END = 5


class replayParser(object):
    def __init__(self, replayfile):

        replay = open(inFile, "rt")
        info = json.loads(replay.readline())

        self.bin = QtCore.qUncompress(QtCore.QByteArray.fromBase64(replay.read()))
        replay.close()        

        #f = open(inFile, 'rb')
        #self.bin = f.read()
        self.offset= 0
        self.supcomVersion = ""
        self.replayVersion = ""
        self.players = []


    def readLine(self, offset):
        line = ''
        while True :
            
            char = struct.unpack("s", self.bin[offset:offset+1])

            offset += 1
            #print char
            if char[0] == '\r' :
                #offset = offset + 2
                break
            elif char[0] == '\x00' :
                #offset = offset + 3
                break
            else :
                line = line + char[0]
        return offset, line
    
    def readInt(self, offset):
        int = struct.unpack("i", self.bin[offset:offset+4])[0]
        return offset+4, int
    
    def readUInt(self, offset):
        int = struct.unpack("I", self.bin[offset:offset+4])[0]
        return offset+4, int

    
    def readChar(self, offset):
        char = struct.unpack("B", self.bin[offset:offset+1])[0]
        return offset+1, char

    
    def readShort(self, offset):
        int = struct.unpack("H", self.bin[offset:offset+2])[0]
        return offset+2, int
    
    def readFloat(self, offset):
        float = struct.unpack("f", self.bin[offset:offset+4])[0]
        return offset+4, float
    
    
    def readBool(self, offset):
        bool = struct.unpack("?", self.bin[offset:offset+1])[0]
        return offset+1, bool
    
    
    def peekType(self, data):
        result = struct.unpack("b", data[0:1])
        return result[0]
    
    def parseLua(self, offset):
    
        type = struct.unpack("b", self.bin[offset:offset+1])[0]
        offset += 1
        #type = struct.unpack("b", data[offset:offset+1])[0]
        
        if type == TYPE_NIL :
            return None
        elif type == TYPE_BOOLEAN :
            return self.readBool(offset)
    
        elif type == TYPE_STRING:
            return self.readLine(offset)
        
        elif type == TYPE_NUMBER:
            return self.readFloat(offset)
            
        elif type == TABLE_BEGIN :
            table = []
            while True :
                type = self.peekType(self.bin[offset:offset+1])
                if type == TABLE_END :
                    break
    
    
                datasKey = self.parseLua(offset)
                key = ''
                if datasKey is not None:
                    off, key = datasKey
                    offset = off
    
                
                datasValue = self.parseLua(offset)
                value = ''
                if datasValue is not None:
                    off, value = datasValue
                    offset =  off 
                    pair = (key, value)
                    table.append(pair)
    
                else :
                    offset += 1
    
            
            return offset+1, table
        
        elif type == TABLE_END :
            raise Exception("Error: unexpected end-of-table")
    
        else :
            raise Exception("Unknown lua data")

    def readHeader(self):
        self.offset, supcomVersion = self.readLine(self.offset)
        self.offset += 3
  

        if supcomVersion.startswith("Supreme Commander v1") == False:
            raise Exception("The file format of this replay is unknown")

        self.supcomVersion = supcomVersion

        self.offset, replayVersion = self.readLine(self.offset)
        self.offset += 1
        

        if replayVersion.startswith("Replay v1.9") == False:
            raise Exception("The file format of this replay is unknown")
        self.replayVersion = replayVersion


        self.offset, map = self.readLine(self.offset)
        print(map)
        self.offset += 4
        
        self.offset, count = self.readInt(self.offset)
        
        
        self.offset = self.offset + count
        
        self.offset, count = self.readInt(self.offset)
        print(count)
        
        self.offset, scenario = self.parseLua(self.offset)
        infos = replayInfos()
        
        
        numSource = struct.unpack("b", self.bin[self.offset:self.offset+1])[0]
        self.offset += 1
        
        for i in range(numSource) :
            self.offset, name = self.readLine(self.offset)
            self.offset, val = self.readInt(self.offset)
        
        
        cheatsEnabled = struct.unpack("b", self.bin[self.offset:self.offset+1])[0]
        self.offset += 1
        
        infos.setCheat(cheatsEnabled)
        
        
        numArmies = struct.unpack("b", self.bin[self.offset:self.offset+1])[0]
        self.offset += 1
        
        armies = replayArmyContainer()
        
        for i in range(0,numArmies) :
            self.offset, val = self.readInt(self.offset)
        
            self.offset, army = self.parseLua(self.offset)
            
            newArmy = ReplayArmy()
            newArmy.populate(army)
            if newArmy.is_player() :
                armies.add(newArmy)
            
            
            b = struct.unpack("b", self.bin[self.offset:self.offset+1])[0]
            self.offset += 1
            if b != -1 :
                #b = struct.unpack("b", self.bin[self.offset:self.offset+1])[0]
                self.offset += 1
                #print b
        
        for army in armies :
            self.players.append(army)
        
        self.offset, randomSeed = self.readInt(self.offset)
        print("randomSeed", randomSeed)


    def setGameTime(self):
        tick = 0
        offset = self.offset
        while offset < len(self.bin):
            offset, message_op = self.readChar(offset)
            offset, message_length = self.readShort(offset)
            if message_op == 0:
                tick += 1
        
            #skip all the data we don't need to look at we're just looking for the time in this function.
            offset = offset + message_length - 3 
        
        return tick
    
    
    def setPlayerLastTurn(self):
        tick = 0
        currentAction = 0
        currentPlayer = 0
        playerturn = 0
        playerLastTurn = {}
        
        offset = self.offset
        while offset < len(self.bin):
            offset, message_op = self.readChar(offset)
            offset, message_length = self.readShort(offset)
            if message_op == 0:
                tick += 1
            elif message_op == 1:
                _, playerturn = self.readChar(offset)
            elif message_op == 11:
                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick
            elif message_op == 12:
                playerLastTurn[playerturn]=tick
            elif message_op == 13:
                playerLastTurn[playerturn]=tick                    
            elif message_op == 19:
                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick
            elif message_op == 22:
                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick                                        
            #skip all the data we don't need to look at we're just looking for the time in this function.
            offset = offset + message_length - 3 
        
        return playerLastTurn

        
    
    def setDebugDesync(self):
        tick = 0
        currentAction = 0
        currentPlayer = 0
        playerturn = 0
        playerLastTurn = {}
        lastbeat = 0
        beatChecksum = {}
        debug = False
        offset = self.offset
        beatDesync = 11450 
        while offset < len(self.bin):
            offset, message_op = self.readChar(offset)
            offset, message_length = self.readShort(offset)
            
            
            if lastbeat == beatDesync or lastbeat == beatDesync-50:

                if message_op != 1 and message_op != 3 and message_op != 12 and message_op != 22: 
                    print(message_op)
                debug = True
            else:
                debug = False
            if message_op == 0:
                
                _, tickToAdvance = self.readInt(offset)
                tick = tick + tickToAdvance 

            elif message_op == 1:
                _, playerturn = self.readChar(offset)
                if debug:
                    print("playerTurn", playerturn) 
            elif message_op == 3:
                #print message_length
                '''CMDST_VerifyChecksum,
                // MD5Digest - checksum
                // uint32 - beat number'''
                fakeoffset = offset
                MD5Digest = ""
                "WARNING: Checksum for beat 1350 mismatched: 68711eb1013370f85ec772abbbf4ac1a (sim) != 45dcf9efa267331f691a87bd47acdb5d (BC_Blackheart)."
                                                             
                for _ in range(16):

                    MD5Digest += (struct.unpack("s", self.bin[fakeoffset:fakeoffset+1])[0]).encode("hex")
                    #MD5Digest =  MD5Digest + struct.unpack("B", self.bin[fakeoffset:fakeoffset+1])[0]
                    fakeoffset += 1
                if debug:
                    print(MD5Digest)
                _, beat = self.readInt(fakeoffset)
                lastbeat = beat

                if not beat in beatChecksum:
                    beatChecksum[beat] = []
                beatChecksum[beat].append(beat)
                if len(beatChecksum[beat]) == len(self.players):
                    #print "beats", beatChecksum[beat]
                    if len( set( beatChecksum[beat] ) ) != 1:
                        
                        print("error on beat", beat, "tick", tick) 

                
            elif message_op == 11:
                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick
            elif message_op == 12:
                if debug:
                    print("CMDST_IssueCommand for player", playerturn) 
                    
                    fakeoffset = offset
                    fakeoffset, numUnits = self.readInt(fakeoffset)
                    for i in range(numUnits):
                        fakeoffset, entityId = self.readInt(fakeoffset)
                        
                    fakeoffset,commandId = self.readInt(fakeoffset)
                    fakeoffset += 4
                    
                    fakeoffset, commandType = self.readChar(fakeoffset)
                    fakeoffset += 4
                    
                    fakeoffset, STITarget = self.readChar(fakeoffset)
                    
                    print("command type", commandType)
                    if commandType == 7 or  commandType == 8 or commandType == 27:
                        if STITarget == 0:
                            fakeoffset += 6
                        elif STITarget == 2:
                            fakeoffset += 1 + 3 * 4 + 1 + 4
                        unitBluePrint = ""
                        for i in range(7):
                            unitBluePrint =  unitBluePrint + struct.unpack("s", self.bin[fakeoffset:fakeoffset+1])[0]
                            fakeoffset += 1
                        print(unitBluePrint)
                    
                
                if currentAction != tick or currentPlayer != playerturn:
                    
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick
                    pass
                playerLastTurn[playerturn]=tick
            elif message_op == 13:
                playerLastTurn[playerturn]=tick                    
            elif message_op == 19:
                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick
            elif message_op == 22:
                
                fakeoffset = offset
                fakeoffset, command = self.readLine(offset) 
                fakeoffset, table = self.parseLua(fakeoffset)
                if debug:
                    print(command, table)
                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick                                        
            #skip all the data we don't need to look at we're just looking for the time in this function.
            offset = offset + message_length - 3 
        
        
        #print val


    def setBuildOrder(self):
        tick = 0
        currentAction = 0
        currentPlayer = 0
        playerturn = 0
        playerLastTurn = {}
        
        offset = self.offset
        while offset < len(self.bin):
            offset, message_op = self.readChar(offset)
            offset, message_length = self.readShort(offset)
            if message_op == 0:
                tick += 1
            elif message_op == 1:
                _, playerturn = self.readChar(offset)
            elif message_op == 11:
                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick
            elif message_op == 12:
                fakeoffset = offset
                fakeoffset, numUnits = self.readInt(fakeoffset)
                for i in range(numUnits):
                    fakeoffset, entityId = self.readInt(fakeoffset)
                    
                fakeoffset,commandId = self.readInt(fakeoffset)
                fakeoffset += 4
                
                fakeoffset, commandType = self.readChar(fakeoffset)
                fakeoffset += 4
                
                fakeoffset, STITarget = self.readChar(fakeoffset)
                
                if currentAction != tick or currentPlayer != playerturn:
                    
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick
                    if commandType == 7 or  commandType == 8 or commandType == 27:
                        if STITarget == 0:
                            fakeoffset += 6
                        elif STITarget == 2:
                            fakeoffset += 1 + 3 * 4 + 1 + 4
                        unitBluePrint = ""
                        for i in range(7):
                            unitBluePrint =  unitBluePrint + struct.unpack("s", self.bin[fakeoffset:fakeoffset+1])[0]
                            fakeoffset += 1
                        print(unitBluePrint)

                                
                        
                playerLastTurn[playerturn]=tick
            elif message_op == 13:
                playerLastTurn[playerturn]=tick                    
            elif message_op == 19:
                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick
            elif message_op == 22:

                if currentAction != tick or currentPlayer != playerturn:
                    currentAction = tick
                    currentPlayer = playerturn
                    playerLastTurn[playerturn]=tick                                        
            #skip all the data we don't need to look at we're just looking for the time in this function.
            offset = offset + message_length - 3         


inFile = r'c:\Users\nozon\Downloads\1265754.fafreplay'

           



replay = replayParser(inFile)
replay.readHeader()
print("gametime", (float(replay.setGameTime()) /10.0) / 60.0, "minutes")

lastTurns= replay.setPlayerLastTurn()
for l in lastTurns :
    print(replay.players[l], ((lastTurns[l] /10.0) / 60.0), "minutes")

replay.setDebugDesync()

    

        
    


