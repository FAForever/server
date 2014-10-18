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

import random



firstvok =["O","U","I","Y","I"]
firstkons = ["T","S","Z","Th","H","V"]
kons = ["n", "t", "h", "s", "z", "th", "tt", "st", "sh", "hw", "ss", "nn", "stl","n", "t", "h", "s", "z","n", "t", "h", "s", "z"]
vok =["a", "y", "u", "o", "ou", "oo", "uo", "ai", "i", "ua", "au", "u", "y", "i", "a","a", "y", "u", "o","a", "y", "u", "o","i","i"]


def generateName() :
    return name(random.randint(0, 2) + 2) + "-" + name(random.randint(0, 3) + 4)             
    
def name(count) :
    vokal = bool(random.getrandbits(1))
    ret = ""
    if vokal :
        ret = ret + random.choice(firstvok)
    else :
        ret = ret + random.choice(firstkons)
     
    for _ in range(count) :
        vokal = not vokal
        if vokal :
            ret = ret + random.choice(vok)
        else :
            ret = ret + random.choice(kons)
    return ret
 
        
    
    
            
    
        
    