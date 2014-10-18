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


import sys
import subprocess
if __name__ == '__main__':

    source = sys.argv[1]
    target = sys.argv[2]
    patchname = sys.argv[3]
   
    patchfile = open(patchname, 'w')
    subprocess.call(['xdelta3', '-I0','-B134217728', '-P16777216', '-W16777216', '-9', '-s', source, target], stdout = patchfile)
    patchfile.close()
