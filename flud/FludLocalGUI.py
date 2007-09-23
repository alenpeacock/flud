
import sys, os, string
import wx

FP_ToBackup = (180,240,180)
FP_ToBackupChild = (210,250,210)
FP_BackedUp = (180,180,240)
FP_BackedUpChild = (210,210,250)
FP_ToExclude = (255,225,225)
FP_ToExcludeChild = (245,235,235)

class FilePanel(wx.Panel):
	def __init__(self, parent, title):
		f = wx.Frame(parent, wx.ID_ANY, title, size=(300,800),
				style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)
		f.Bind(wx.EVT_CLOSE, self.shutdown)

		# Use the WANTS_CHARS style so the panel doesn't eat the Return key.
		wx.Panel.__init__(self, f, -1, style=wx.WANTS_CHARS)
		self.Bind(wx.EVT_SIZE, self.OnSize)

		self.dirtree = wx.GenericDirCtrl(self, -1, size=(300,800), 
				style=wx.TR_MULTIPLE)  # XXX: Multiple selection no-worky
		self.tree = self.dirtree.GetTreeCtrl()

		self.Bind(wx.EVT_TREE_ITEM_EXPANDED, self.OnItemExpanded, self.tree)
		#self.Bind(wx.EVT_TREE_ITEM_COLLAPSED, self.OnItemCollapsed, self.tree)
		self.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged, self.tree)
		self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate, self.tree)

		self.tree.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDClick)
		self.tree.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
		self.tree.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)

		self.color = {}
		self.FP_Default = self.tree.GetItemBackgroundColour(
				self.tree.GetRootItem())

		self.states = {} # dict of filepaths, True=backup, False=exclude
		self.fludfiles = self.getFludHome()+"/fludfile.conf"
		if os.path.isfile(self.fludfiles):
			file = open(self.fludfiles, 'r')
			self.states = eval(file.read())
			file.close()
			self.renderChildren(self.tree.GetRootItem(), True)

		f.Show(True)

	def getFludHome(self):
		if os.environ.has_key('FLUDHOME'):
			fludhome = os.environ['FLUDHOME']
		else:
			fludhome = os.environ['HOME']+"/.flud"
		if not os.path.isdir(fludhome):
			os.mkdir(fludhome, 0700)
		return fludhome	

	def renderChildren(self, parent, recurse=False):
		parentstate = self.tree.GetItemBackgroundColour(parent)
		children = self.getChildren(parent, False)
		for i in children:
			path = self.getFullPath(i)
			if self.states.has_key(path):
				color = FP_ToExclude
				if self.states[path]:
					color = FP_ToBackup
				self.tree.SetItemBackgroundColour(i, color)
			elif parentstate == FP_ToBackup \
					or parentstate == FP_ToBackupChild:
				self.tree.SetItemBackgroundColour(i, FP_ToBackupChild)
			elif parentstate == FP_ToExclude \
					or parentstate == FP_ToExcludeChild:
				self.tree.SetItemBackgroundColour(i, FP_ToExcludeChild)
			elif parentstate == self.FP_Default:
				self.tree.SetItemBackgroundColour(i, self.FP_Default)
			if recurse:
				self.renderChildren(i,recurse)

	def getChildren(self, node, recurse=False):
		result = []
		child, cookie = self.tree.GetFirstChild(node)
		while child:
			result.append(child)
			if recurse:
				result.extend(self.getChildren(child, recurse))
			child, cookie = self.tree.GetNextChild(node, cookie)
		return result

	def getFullPath(self, node):
		path = self.tree.GetItemText(node)
		n = node
		while True:
			n = self.tree.GetItemParent(n)
			if n and n != self.tree.GetRootItem():
				path = self.tree.GetItemText(n)+'/'+path
			else:
				break
		return path

	def walkTree(self, startnode, parentpath="", recurse=True):
		child, cookie = self.tree.GetFirstChild(startnode)
		while child:
			path = "%s/%s" % (parentpath, self.tree.GetItemText(child))
			print path
			if recurse:
				self.walkTree(child, path)
			child, cookie = self.tree.GetNextChild(startnode, cookie)

	def shutdown(self, event):
		f = open(self.fludfiles, 'w')
		f.write(str(self.states))
		f.close()
		for i in self.states:
			# XXX: need to communicate the backup of the indicated files.
			#      perhaps this is done entirely by the file we just saved...
			print "%s %s" % (i, self.states[i])
		event.Skip()

	def OnRightDown(self, event):
		pt = event.GetPosition();
		item, flags = self.tree.HitTest(pt)
		if item:
			#print "OnRightClick: %s, %s, %s" % (self.tree.GetItemText(item), 
			#		type(item), item.__class__)
			#self.tree.SelectItem(item)
			pass

	def OnRightUp(self, event):
		pt = event.GetPosition();
		item, flags = self.tree.HitTest(pt)
		if item:        
			#print "OnRightUp: %s" % self.tree.GetItemText(item)
			#self.tree.EditLabel(item)
			pass

	def OnLeftDClick(self, event):
		#pt = event.GetPosition();
		#item, flags = self.tree.HitTest(pt)
		#if item:
		#    self.log.WriteText("OnLeftDClick: %s\n" 
		#		% self.tree.GetItemText(item))
		#    parent = self.tree.GetItemParent(item)
		#    if parent.IsOk():
		#        self.tree.SortChildren(parent)
		event.Skip()

	def OnSize(self, event):
		w,h = self.GetClientSizeTuple()
		self.tree.SetDimensions(0, 0, w, h)

	def OnItemExpanded(self, event):
		item = event.GetItem()
		if item:
			#print "OnItemExpanded: %s" % self.tree.GetItemText(item)
			self.renderChildren(item)

	def OnItemCollapsed(self, event):
		item = event.GetItem()
		if item:
			#print "OnItemCollapsed: %s" % self.tree.GetItemText(item)
			pass

	def OnSelChanged(self, event):
		#self.item = event.GetItem()
		#if self.item:
		#	print "OnSelChanged: %s" % self.tree.GetItemText(self.item)
		#	if wx.Platform == '__WXMSW__':
		#		print "BoundingRect: %s" % self.tree.GetBoundingRect(self.item,
		#			   	True)
		#	#items = self.tree.GetSelections()
		#	#print map(self.tree.GetItemText, items)
		event.Skip()

	def OnActivate(self, event):
		item = event.GetItem()
		if item:
			parent = self.tree.GetItemParent(item)
			parentState = self.tree.GetItemBackgroundColour(parent)
			path = self.getFullPath(item)
			#print "OnActivate: path = '%s'" % path	
			stateColor = self.tree.GetItemBackgroundColour(item)
			# XXX: currently, users can't toggle children of 'Exclude' to
			# 'ToBackup'
			# If a parent directory is excluded, none of its children can be set
			# to ToBackup.  This makes sense, since parent directory information
			# is needed to store a file, and if the parent is excluded, we
			# can't do it.  There are two options: 1) when user selects a child
			# of an excluded parent, set the parent(s) to 'ToBackup' 
			# automatically (which implies setting all the peer files in the
			# dir to Default) or 2) in the message area, point out that in
			# order in configure a file for backup, the parent must be selected
			# for backup too.
			if stateColor == self.FP_Default:
				self.tree.SetItemBackgroundColour(item, FP_ToBackup)
				self.states[path] = True
				self.renderChildren(item, True)
			elif stateColor == FP_ToBackup or stateColor == FP_ToBackupChild:
				self.tree.SetItemBackgroundColour(item, FP_ToExclude)
				self.states[path] = False
				self.renderChildren(item, True)
			else:
				self.tree.SetItemBackgroundColour(item, self.FP_Default)
				if self.states.has_key(path):
					self.states.pop(path)
				if parentState == self.FP_Default:
					self.renderChildren(item, True)
				else:
					self.renderChildren(parent, True)
			
			self.tree.UnselectItem(item)



if __name__ == '__main__':
	app = wx.PySimpleApp()
	f = FilePanel(None, "flud backup client")
	app.MainLoop()

