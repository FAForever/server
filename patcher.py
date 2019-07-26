import sys
import subprocess
if __name__ == '__main__':

    source = sys.argv[1]
    target = sys.argv[2]
    patchname = sys.argv[3]
   
    patchfile = open(patchname, 'w')
    subprocess.call(['xdelta3', '-I0','-B134217728', '-P16777216', '-W16777216', '-9', '-s', source, target], stdout = patchfile)
    patchfile.close()
