"""\
Common bits and pieces used by the various bots.
"""

import sys
import os
import time
from threading import Thread, Event


class OutputManager(Thread):
  def __init__(self, connection, delay=.5):
    Thread.__init__(self)
    self.setDaemon(1)
    self.connection = connection
    self.delay = delay
    self.event = Event()
    self.queue = []

  def run(self):
    while 1:
      self.event.wait()
      while self.queue:
        msg,target = self.queue.pop(0)
        self.connection.privmsg(target, msg)
        time.sleep(self.delay)
      self.event.clear()

  def send(self, msg, target):
    self.queue.append((msg.strip(),target))
    self.event.set()


def trivial_bot_main(klass):
  if len(sys.argv) != 4:
    botname = os.path.basename(sys.argv[0])
    print "Usage: %s <server[:port]> <channel> <nickname>" % botname
    sys.exit(1)

  s = sys.argv[1].split(":", 1)
  server = s[0]
  if len(s) == 2:
    try:
      port = int(s[1])
    except ValueError:
      print "Error: Erroneous port."
      sys.exit(1)
  else:
    port = 6667
  channel = sys.argv[2]
  nickname = sys.argv[3]

  klass(channel, nickname, server, port).start()