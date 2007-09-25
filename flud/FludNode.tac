#!/usr/bin/python
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
service = node.start(twistd=True)
#service.setServiceParent(application)
