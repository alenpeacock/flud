#!/usr/bin/python
"""
FludTestGauges.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL).

Provides gauges for visualizing storage for multiple flud nodes running on 
the same host.  This is really only useful for demos and testing.
"""
import sys, os, stat, random
import wx
import wx.lib.buttons as buttons
from FludConfig import FludConfig

dutotal = 0
def visit(arg, top, files):
	global dutotal
	for file in files:
		dutotal += os.lstat("%s" % (os.path.join(top,file)))[stat.ST_SIZE]
	arg += dutotal

def du(dir):
	global dutotal
	dutotal = 0
	os.path.walk(dir, visit, dutotal)
	return dutotal

# XXX: too much manual layout.  should convert to a managed layout to allow for
# resizing, etc.
SGAUGEWIDTH = 260  # storage gauge
DGAUGEWIDTH = 100  # dht gauge
GAUGEHEIGHT = 20
ROWHEIGHT = 30
SEP = 5
LABELWIDTH = 45
POWERWIDTH = 70
RATIOBARHEIGHT = 70
COLWIDTH = SGAUGEWIDTH+DGAUGEWIDTH+LABELWIDTH+POWERWIDTH

class FludTestGauges(wx.Frame):

	def __init__(self, parent, title, dirroot, dirs):
		screenHeight = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_Y)-100
		rowheight = ROWHEIGHT+SEP
		height = len(dirs)*(rowheight)+RATIOBARHEIGHT
		columns = height / screenHeight + 1 
		width = COLWIDTH*columns
		if columns > 1:
			height = (len(dirs)/columns)*(rowheight)+RATIOBARHEIGHT
			if (len(dirs) % columns) > 0:
				height += rowheight

		wx.Frame.__init__(self, parent, wx.ID_ANY, title, size=(width,height),
				style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)

		self.storebarend = 8192	
		self.smultiplier = 100.0 / self.storebarend
		self.sdivisor = 1
		self.sbytelabel = ""
		self.dhtbarend = 512
		self.dmultiplier = 100.0 / self.dhtbarend
		self.ddivisor = 1
		self.dbytelabel = ""

		self.storeheading = wx.StaticText(self, -1, "block storage",
				(LABELWIDTH, 5))
		self.totaldht = wx.StaticText(self, -1, "metadata",
				(LABELWIDTH+SGAUGEWIDTH+SEP, 5))
		self.gauges = []
		curCol = 0
		curRow = 30
		for i in range(len(dirs)):
			self.gauges.append(wx.Gauge(self, -1, 100, 
					(curCol*COLWIDTH+LABELWIDTH, curRow),
					(SGAUGEWIDTH, GAUGEHEIGHT)))
			self.gauges[i].SetBezelFace(3)
			self.gauges[i].SetShadowWidth(3)
			self.gauges[i].SetValue(0)
			self.gauges[i].dir = "%s%s" % (dirroot,dirs[i])
			os.environ['FLUDHOME'] = self.gauges[i].dir;
			conf = FludConfig()
			conf.load(doLogging = False)
			print "%s" % conf.nodeID
			self.gauges[i].idlabel = wx.StaticText(self, -1, "%s" % conf.nodeID,
					(curCol*COLWIDTH+LABELWIDTH, curRow+20))
			font = self.gauges[i].idlabel.GetFont()
			font.SetPointSize(6)
			self.gauges[i].idlabel.SetFont(font)
			self.gauges[i].label = wx.StaticText(self, -1, "%s" % dirs[i], 
					(curCol*COLWIDTH+15, curRow+(rowheight/4)))
			self.gauges[i].dhtgauge = wx.Gauge(self, -1, 100,
					(curCol*COLWIDTH+LABELWIDTH+SGAUGEWIDTH+SEP, curRow), 
					(SGAUGEWIDTH/3, GAUGEHEIGHT))
			self.gauges[i].button = wx.Button(self, i, "power",
					(curCol*COLWIDTH
						+LABELWIDTH+SGAUGEWIDTH+2*SEP+SGAUGEWIDTH/3, 
						curRow),
					(POWERWIDTH, ROWHEIGHT))
			#self.gauges[i].button = buttons.GenBitmapToggleButton(self, i, 
			#		None, 
			#		(LABELWIDTH+SGAUGEWIDTH+2*SEP+SGAUGEWIDTH/3, curRow),
			#		(POWERWIDTH, ROWHEIGHT))
			#self.gauges[i].button.SetBestSize()
			self.gauges[i].button.SetToolTipString("press me to shut down")
			self.Bind(wx.EVT_BUTTON, self.onClick, self.gauges[i].button)

			curRow += rowheight
			if curRow > height-RATIOBARHEIGHT:
				curCol += 1
				curRow = 30

		self.totalstore = wx.StaticText(self, -1, "total: 0",
				(LABELWIDTH, height-40))
		self.totaldht = wx.StaticText(self, -1, "total: 0",
				(LABELWIDTH+SGAUGEWIDTH+SEP, height-40))
		self.ratiogauge = wx.Gauge(self, -1, 100, (LABELWIDTH, height-20), 
				(SGAUGEWIDTH+SEP+SGAUGEWIDTH/3, 10))
		self.ratiogauge.SetValue(0)

		self.Bind(wx.EVT_IDLE, self.IdleHandler)

		self.timer = wx.PyTimer(self.update)
		self.timer.Start(1000)

	def onClick(self, event):
		print "click! %s" % event.GetId()

	def update(self):

		def sizeclass(num):
			divisor = 1
			bytelabel = ""
			if num > 1024:
				divisor = 1024.0
				bytelabel = 'K'
			if num > 1048576:
				divisor = 1048576.0
				bytelabel = 'M'
			if num > 1073741824:
				divisor = 1073741824.0
				bytelabel = 'G'
			return (divisor, bytelabel)

		storelargest = 0
		dhtlargest = 0
		storetotal = 0
		dhttotal = 0
		for i in self.gauges:
			if os.path.isdir(i.dir):
				i.storebytes = du(os.path.join(i.dir,'store'))
				if i.storebytes > storelargest:
					storelargest = i.storebytes
				storetotal += i.storebytes
				i.dhtbytes = du(os.path.join(i.dir,'dht'))
				if i.dhtbytes > dhtlargest:
					dhtlargest = i.dhtbytes
				dhttotal += i.dhtbytes
			else:
				i.storebytes = 0
				i.dhtbytes = 0
				i.Disable()
				i.button.Disable()

		while storelargest > self.storebarend:
			self.storebarend = self.storebarend * 2
			self.smultiplier = 100.0 / self.storebarend
		self.sdivisor, self.sbytelabel = sizeclass(storetotal)
		while dhtlargest > self.dhtbarend:
			self.dhtbarend = self.dhtbarend * 2
			self.dmultiplier = 100.0 / self.dhtbarend
		self.ddivisor, self.dbytelabel = sizeclass(dhttotal)


		#print "-----"
		for i in self.gauges:
			i.SetValue(i.storebytes*self.smultiplier)
			i.dhtgauge.SetValue(i.dhtbytes*self.dmultiplier)
			#print "%.2f, %.2f" % ((float(i.storebytes)/float(i.dhtbytes)), 
			#		(float(i.GetValue())/float(i.dhtgauge.GetValue())))

		self.totalstore.SetLabel("total: %.1f%s" 
				% (float(storetotal)/self.sdivisor, self.sbytelabel))
		self.totaldht.SetLabel("total: %.1f%s" 
				% (float(dhttotal)/self.ddivisor, self.dbytelabel))
		if (dhttotal+storetotal == 0):
			self.ratiogauge.SetValue(0)
		else:
			self.ratiogauge.SetValue((storetotal*100/(dhttotal+storetotal)))

	def updateGauges(self, update):
		for index, value in update:
			self.monitors[index].setValue(value)

	def IdleHandler(self, event):
		pass

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print "usage: %s dircommon exts" % sys.argv[0]
		print "  where exts will be appended to dircommon"
		print "  e.g., '%s /home/joe/.flud 1,2,3,4,10,15,20'"\
				% sys.argv[0]
		print "  or, '%s /home/joe/.flud 1-10,15,20'"\
				% sys.argv[0]
		sys.exit()
	root = sys.argv[1]
	exts = []
	for i in sys.argv[2].split(','):
		if i.find('-') >= 0:
			start, end = i.split('-')
			for j in range(int(start),int(end)+1):
				exts.append(j)
		else:
			exts.append(int(i))

	app = wx.PySimpleApp()
	t = FludTestGauges(None, 'Flud Test Gauges', root, exts)
	t.Show(1)
	app.MainLoop()
