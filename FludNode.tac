#!/usr/bin/python
"""
FludNode.tac (c) 2003-2006 Alen Peacock.  This program is distributed under the
terms of the GNU General Public License (the GPL).

This is the application file used by twistd to daemonize FludNode.
"""

import FludNode
from protocol.FludCommUtil import getCanonicalIP
from twisted.application import service, internet
import os

port = None
gwhost = None
gwport = None

if 'FLUDPORT' in os.environ:
	port = int(os.environ['FLUDPORT'])

if 'FLUDGWHOST' in os.environ:
	gwhost = getCanonicalIP(os.environ['FLUDGWHOST'])

if 'FLUDGWPORT' in os.environ:
	gwport = int(os.environ['FLUDGWPORT'])

node = FludNode.FludNode(port)
if gwhost and gwport:
	node.connectViaGateway(gwhost, gwport)

application = service.Application("FludNode")
service = node.start(twistd=True)
#service.setServiceParent(application)
