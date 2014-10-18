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

import struct

class Packet():
    def __init__(self, headersize=None , data=None, *values, **kwvalues):
        self._data = data
        self._values = kwvalues
        self._headersize = headersize
          
    def Unpack(self, data=None):
        print "UNPACK"
        if not data:
            data = self._data
        unpacked = {}
        maxData = 0
        while data:
            maxData = maxData + 1
            if maxData > 50 : break
            
            headerSize = struct.unpack("i", data[:4])[0]
            
            print "headerSize", headerSize
            
            headerPackStr = "<i" + str(headerSize) + "si"
            header = struct.unpack(headerPackStr, data[:headerSize+8])
            
            print "header", header
            
            headerStr = header[1].replace("/t","\t").replace("/n","\n")
            if not unpacked.has_key(header[1]):
                unpacked[headerStr] = []
            chunkSize = header[2]
            data = data[headerSize+8:]
            print "chunkSize", chunkSize
            print "data", data
            chunk = []
            for i in range(chunkSize):
                fieldType = struct.unpack("b", data[:1])[0]
                if fieldType is 0:
                    number = struct.unpack("i", data[1:5])[0]
                    chunk.append(number)
                    data = data[5:]
                else:
                    fieldSize = struct.unpack("i", data[1:5])[0]
                    packStr = str(fieldSize) + "s"
                    string = struct.unpack(packStr, data[5:fieldSize+5])[0]
                    fixedStr = string.replace("/t","\t").replace("/n","\n")
                    chunk.append(fixedStr)
                    data = data[fieldSize+5:]
            unpacked[headerStr].extend([chunk])
        self._values = unpacked
        return unpacked


    def Pack(self):
        if self._data:
            return self._data
        data = ""
        for i, chunk in self._values.iteritems():
            headerSize = len(str(i))
            headerField = str(i).replace("\t","/t").replace("\n","/n")
            chunkSize = len(chunk)
            headerPackStr = "<i" + str(headerSize) + "si"
            data += struct.pack(headerPackStr, headerSize, headerField, chunkSize)
            chunkType = type(chunk)
            if chunkType is list:
                for field in chunk:
                    fieldType = 0 if type(field) is int else 1
                    chunkPackStr = ""
                    fields = []
                    if fieldType is 1:
                        fieldSize = len(field)
                        chunkPackStr += "<bi" + str(fieldSize) + "s"
                        fieldStr = field.replace("\t","/t").replace("\n","/n")
                        fields.extend([fieldType, fieldSize, fieldStr])
                    elif fieldType is 0:
                        chunkPackStr += "<bi"
                        fields.extend([fieldType, field])
                    data += struct.pack(chunkPackStr, *fields)
        return data


    def PackUdp(self):
        if self._data:
            return self._data
        data = ""
        for i, chunk in self._values.iteritems():
            headerSize = len(str(i))
            headerField = str(i).replace("\t","/t").replace("\n","/n")
            chunkSize = len(chunk)
            headerPackStr = "<i" + str(headerSize) + "si"
            data += struct.pack(headerPackStr, headerSize, headerField, chunkSize)
            chunkType = type(chunk)
            i = 0
            if chunkType is list:
                
                for field in chunk:

                    fieldType = 0 if type(field) is int else 1

                    chunkPackStr = ""
                    fields = []
                    if fieldType is 1:

                        datas = "\x08"
                        if i == 1 :
                            fieldSize = len(field) + len(datas)
                        else :
                            fieldSize = len(field)
                            
                        chunkPackStr += "<bi" + str(fieldSize) + "s"
                        fieldStr = field.replace("\t","/t").replace("\n","/n")
                        if i == 1 :
                            fields.extend([2, fieldSize, datas+fieldStr])
                        else :
                            fields.extend([fieldType, fieldSize, fieldStr])
                    elif fieldType is 0:
                        chunkPackStr += "<bi"
                        fields.extend([fieldType, field])
                    data += struct.pack(chunkPackStr, *fields)
                    i = 1
        return data
        
