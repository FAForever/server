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


from PySide import QtCore

UNIT16 = 8
import sys


def runGW():
    
    #create server singleton and connect
    import gwserver       
    gw_server = gwserver.instance
    gw_server.setup()
    QtCore.QCoreApplication.exec_()




#Actual "main" method 
if __name__ == '__main__':             

    #init application framework    
    
    app = QtCore.QCoreApplication(sys.argv)
    
    
    if len(sys.argv) == 1:
        #Do the magic    
        runGW()



    
    



            
            

