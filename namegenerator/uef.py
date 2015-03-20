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


girl = 'namegenerator/races/dist.female.first'
male = 'namegenerator/races/dist.male.first'
last = 'namegenerator/races/dist.all.last'
import string

import random


def generateName() :
    female = bool(random.getrandbits(1))
    if female :
        lines = open(girl).read().splitlines()
    else :
        lines = open(male).read().splitlines()
        
    myline =random.choice(lines)
        
    lines = open(last).read().splitlines()

    return string.capitalize(myline) + " " + string.capitalize(random.choice(lines))
