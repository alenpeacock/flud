#!/usr/bin/env python3
"""
FludNode.tac (c) 2003-2006 Alen Peacock.  This program is distributed under the
terms of the GNU General Public License (the GPL).

This is the application file used by twistd to daemonize FludNode.
"""

import os
from twisted.application import service, internet

import flud.FludNode
from flud.protocol.FludCommUtil import getCanonicalIP

port = None
gwhost = None
gwport = None

if 'FLUDPORT' in os.environ:
	port = int(os.environ['FLUDPORT'])

if 'FLUDGWHOST' in os.environ:
	gwhost = getCanonicalIP(os.environ['FLUDGWHOST'])

if 'FLUDGWPORT' in os.environ:
	gwport = int(os.environ['FLUDGWPORT'])

node = flud.FludNode.FludNode(port)
if gwhost and gwport:
	node.connectViaGateway(gwhost, gwport)

application = service.Application("flud.FludNode")

class FludService(service.Service):
	def startService(self):
		service.Service.startService(self)
		node.start(twistd=True)

	def stopService(self):
		node.stop()

flud_service = FludService()
flud_service.setServiceParent(application)
