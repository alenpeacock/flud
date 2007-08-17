#!/usr/bin/python

"""
FludClient.py, (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 2.

FludClient provides a GUI Client for interacting with FludNode.
"""

from twisted.internet import wxreactor
wxreactor.install()

import sys, os, string, time, glob
import wx
import wx.lib.mixins.listctrl as listmix
import wx.lib.editor.editor
from Protocol.LocalClient import *
from FludConfig import FludConfig


mimeMgr = wx.MimeTypesManager()

def getFileIcon(file, il, checkboxes, icondict):
	ft = mimeMgr.GetFileTypeFromExtension(file[file.rfind('.')+1:])
	# XXX: what about from mimetype or magic?
	if ft == None:
		return icondict['generic']
	else:
		desc = ft.GetDescription()
		if icondict.has_key(desc):
			return icondict[desc]
		else:
			icon = ft.GetIcon()
			if icon == None or not icon.Ok():
				#print "couldn't find an icon image for %s" % file
				icondict[desc] = icondict['generic']
				return icondict[desc]
			bm = wx.BitmapFromIcon(icon)
			newimages = makeCheckboxBitmaps(bm, checkboxes)
			#il = self.GetImageList()
			pos = il.GetImageCount()
			for i in newimages:
				il.Add(i)
			icondict[desc] = pos
			#print "%s got a %s image" % (file, ft.GetDescription())
			return pos

def getEmptyBitmapAndDC(width, height):
	empty = wx.EmptyBitmap(width,height)
	temp_dc = wx.MemoryDC()
	temp_dc.SelectObject(empty)
	temp_dc.Clear()
	return (empty, temp_dc)

def makeCheckboxBitmaps(basebitmap, checkboxes):
	if basebitmap.GetWidth() != 16 or basebitmap.GetHeight() != 16:
		img = basebitmap.ConvertToImage()
		img.Rescale(16, 16)
		basebitmap = img.ConvertToBitmap()
	result = []
	for i in checkboxes:
		bm, dc = getEmptyBitmapAndDC(40,16)
		dc.DrawBitmap(basebitmap, 0, 0, False)
		dc.DrawBitmap(i, 20, 2, False)
		result.append(bm)
	return result

def createDefaultImageList():
	def getDefaultCheckboxes():
		ucbm = wx.BitmapFromImage(wx.Image("checkbox-unchecked1.png"))
		cbm = wx.BitmapFromImage(wx.Image("checkbox-checked1.png"))
		ccbm = wx.BitmapFromImage(wx.Image("checkbox-checkedpartial1.png"))
		cpbm = wx.BitmapFromImage(wx.Image("checkbox-parentchecked1.png"))
		ebm = wx.BitmapFromImage(wx.Image("checkbox-excluded1.png"))
		ecbm = wx.BitmapFromImage(wx.Image("checkbox-excludedpartial1.png"))
		return (ucbm, cbm, ccbm, cpbm, ebm, ecbm)
	checkboxes = getDefaultCheckboxes()
		
	il = wx.ImageList(40, 16)
	folderimgs = makeCheckboxBitmaps(wx.ArtProvider_GetBitmap(
		wx.ART_FOLDER, wx.ART_CMN_DIALOG, wx.Size(16, 16)), checkboxes)
	computer = makeCheckboxBitmaps(wx.ArtProvider_GetBitmap(
		wx.ART_HARDDISK, wx.ART_CMN_DIALOG, wx.Size(16, 16)), checkboxes)
	drives = makeCheckboxBitmaps(wx.ArtProvider_GetBitmap(
		wx.ART_HARDDISK, wx.ART_CMN_DIALOG, wx.Size(16, 16)), checkboxes)
	cdrom = makeCheckboxBitmaps(wx.ArtProvider_GetBitmap(
		wx.ART_CDROM, wx.ART_CMN_DIALOG, wx.Size(16, 16)), checkboxes)
	floppy = makeCheckboxBitmaps(wx.ArtProvider_GetBitmap(
		wx.ART_FLOPPY, wx.ART_CMN_DIALOG, wx.Size(16, 16)), checkboxes)
	removable = makeCheckboxBitmaps(wx.ArtProvider_GetBitmap(
		wx.ART_REMOVABLE, wx.ART_CMN_DIALOG, wx.Size(16, 16)), checkboxes)
	genericfile = makeCheckboxBitmaps(wx.ArtProvider_GetBitmap(
		wx.ART_NORMAL_FILE, wx.ART_CMN_DIALOG, wx.Size(16, 16)), checkboxes)
	execfile = makeCheckboxBitmaps(wx.ArtProvider_GetBitmap(
		wx.ART_EXECUTABLE_FILE, wx.ART_CMN_DIALOG, wx.Size(16, 16)), checkboxes)
	j = 0
	icondict = {}
	icondict['folder'] = j
	for i in folderimgs:
		il.Add(i)
		j = j+1
	icondict['computer'] = j
	for i in computer:
		il.Add(i)
		j = j+1
	icondict['drives'] = j
	for i in drives:
		il.Add(i)
		j = j+1
	icondict['cdrom'] = j
	for i in cdrom:
		il.Add(i)
		j = j+1
	icondict['floppy'] = j
	for i in floppy:
		il.Add(i)
		j = j+1
	icondict['removable'] = j
	for i in removable:
		il.Add(i)
		j = j+1
	icondict['generic'] = j
	for i in genericfile:
		il.Add(i)
		j = j+1
	icondict['exec'] = j
	for i in execfile:
		il.Add(i)
		j = j+1
	return il, checkboxes, icondict

class CheckboxState:
	(UNSELECTED, SELECTED, SELECTEDCHILD, SELECTEDPARENT, EXCLUDED, 
			EXCLUDEDCHILD) = range(6)
	
	def offset(oldstate, newstate):
		return newstate - oldstate
	offset = staticmethod(offset)

class DirCheckboxCtrl(wx.TreeCtrl):
	
	def __init__(self, parent, id=-1, dir=None, pos=wx.DefaultPosition, 
			size=wx.DefaultSize, 
			style=(wx.TR_MULTIPLE 
				| wx.TR_HAS_BUTTONS 
				| wx.TR_TWIST_BUTTONS 
				| wx.TR_NO_LINES 
				| wx.TR_FULL_ROW_HIGHLIGHT
				| wx.SUNKEN_BORDER), 
			validator=wx.DefaultValidator, name=wx.ControlNameStr,
			allowExclude=True):
		self.allowExclude = allowExclude
		wx.TreeCtrl.__init__(self, parent, id, pos, size, style, validator,
				name)
		self.listeners = []

		#self.il = self.GetImageList()
		#self.checkboxes = self.getDefaultCheckboxes()
		self.expandRoot(dir)
		self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.onExpand, self)
		self.Bind(wx.EVT_LEFT_UP, self.onClick, self)
		self.Bind(wx.EVT_TREE_ITEM_GETTOOLTIP, self.onTooltip, self)

	def expandRoot(self, dir):
		if not os.path.isdir(dir):
			raise ValueError("%s is not a valid directory path")
		
		self.defaultImageList, self.checkboxes, self.icondict \
				= createDefaultImageList()
		self.AssignImageList(self.defaultImageList)
		self.il = self.GetImageList()
		if dir == None: 
			self.rootID = self.AddRoot(dir, self.icondict['computer'], -1, 
					wx.TreeItemData((dir, True, False, 
						CheckboxState.UNSELECTED)))
			# XXX: getTopLevelDirs() and add them as children
		else:
			self.rootID = self.AddRoot(dir, self.icondict['folder'], -1, 
					wx.TreeItemData((dir, True, False, 
						CheckboxState.UNSELECTED)))
		self.expandDir(self.rootID)
		self.Expand(self.rootID)
		
	def expandDir(self, parentID, hideHidden=False, busycursor=True):
		def isDriveAvailable(path):			
			if len(path) == 2 and path[1] == ':':
				path = path.lower()
				if path[0] == 'a' or path[0] == 'b' or diExists(path):
					return True
				else:
					return False
			return True

		(path, isDir, expanded, state) = self.GetItemData(parentID).GetData()
		if expanded:
			return
		if not isDriveAvailable(path):
			return
		if busycursor: wx.BusyCursor()
		try:
			dirlist = os.listdir(path)
		except:
			self.SetItemHasChildren(parentID, False)
			return
		
		if len(dirlist) == 0:
			self.SetItemHasChildren(parentID, False)
			return
		dirs = []
		files = []
		for i in dirlist:
			if hideHidden:
				# XXX: if this is a hidden file, don't add it.
				pass
			elif os.path.isdir(os.path.join(path,i)):
				dirs.append(i)
			else:
				files.append(i)
		dirs.sort()
		files.sort()
		for d in dirs:
			child = self.AppendItem(parentID, d)
			self.SetPyData(child, (os.path.join(path,d), True, False, 0))
			self.SetItemImage(child, self.icondict['folder'], 
					wx.TreeItemIcon_Normal)
			self.SetItemHasChildren(child)
		il = self.GetImageList()
		for f in files:
			child = self.AppendItem(parentID, f) # XXX: unicode?
			self.SetPyData(child, (os.path.join(path,f), False, False, 0))
			idx = getFileIcon(os.path.join(path,f), il, self.checkboxes, 
					self.icondict)
			self.SetItemImage(child, idx, wx.TreeItemIcon_Normal)

		self.SetPyData(parentID, (path, isDir, True, state))
	
	def getStates(self, node=None):
		if not node:
			node = self.rootID
		states = {}
		(path, isDir, expanded, state) = self.GetItemData(node).GetData()
		if state in [CheckboxState.SELECTED, CheckboxState.EXCLUDED]:
			states[path] = state
		children = self.getChildren(node, False)
		for child in children:
			states.update(self.getStates(child))
		return states
		
	def setStates(self, states):
		for i in states:
			found = self.findNode(i)
			if found:
				self.setItemState(found, states[i])

	def findNode(self, path):
		if path[0] == '/':
			path = path[1:]  # XXX: unix only
		traversal = path.split(os.path.sep)
		if traversal[0] == '':
			traversal.remove('')
		node = self.rootID
		while True:
			(ipath, isdir, expanded, istate) = self.GetItemData(node).GetData()
			if len(traversal) == 0:
				return node
			self.expandDir(node)
			children = self.getChildren(node, False)
			childrennames = [self.GetItemText(x) for x in children]
			firstpath = traversal[0]
			if firstpath in childrennames:
				p = childrennames.index(firstpath)
				node = children[p]
				traversal.remove(firstpath)
			else:
				#print "  the file %s is no longer present!" % path
				return None
		return None
			
	
	def onExpand(self, event):
		self.expandDir(event.GetItem())
		self.renderChildren(event.GetItem(), True)

	def getFullPath(self, node):
		path = self.tree.GetItemText(node)
		n = node
		while True:
			n = self.tree.GetItemParent(n)
			if n and n != self.GetRootItem():
				path = os.path.join(self.tree.GetItemText(n),path)
			else:
				break
		return path

	def renderParents(self, item):
		if item == self.rootID:
			return
		n = item
		(path, isDir, expanded, state) = self.GetItemData(item).GetData()
		while True:
			n = self.GetItemParent(n)
			(parentpath, parentisDir, parentexpanded, 
					parentstate) = self.GetItemData(n).GetData()
			#print "parent %s" % parentpath
			if n and n != self.GetRootItem():
				newstate = parentstate
				if parentstate != CheckboxState.UNSELECTED and \
						parentstate != CheckboxState.SELECTEDPARENT:
					# we only care about changing UNSELECT or SELECTEDPARENT
					# states
					break
				else:
					if state == CheckboxState.SELECTED or \
							state == CheckboxState.SELECTEDCHILD or \
							state == CheckboxState.SELECTEDPARENT:
						# if the item (child) is selected in any way, parent
						# should be too.
						newstate = CheckboxState.SELECTEDPARENT
					elif state == CheckboxState.UNSELECTED or \
							state == CheckboxState.EXCLUDED:
						# if the item (child) is unselected or excluded, the
						# parent should be too, /unless/ there are other
						# children at the same level who are selected.
						children = self.getChildren(n, False)
						newstate = CheckboxState.UNSELECTED
						for child in children:
							(cpath, cisdir, cexp, 
									cstate) = self.GetItemData(child).GetData()
							if cstate == CheckboxState.SELECTED or \
									cstate == CheckboxState.SELECTEDCHILD or \
									cstate == CheckboxState.SELECTEDPARENT:
								newstate = parentstate
						if newstate == parentstate:
							break
					imageidx = self.GetItemImage(n)
					imageidx += CheckboxState.offset(parentstate, newstate)
					self.SetPyData(n, (parentpath, parentisDir, 
						parentexpanded, newstate))
					self.SetItemImage(n, imageidx) 
			else:
				break

	def renderChildren(self, parent, recurse=False):
		(parentpath, parentisDir, parentexpanded, 
				parentstate) = self.GetItemData(parent).GetData()
		children = self.getChildren(parent, False)
		for child in children:
			#path = self.getFullPath(child)
			(path, isDir, expanded, state) = self.GetItemData(child).GetData()
			imageidx = self.GetItemImage(child)
			newstate = state
			"""
			Here are the state transitions for children based on current states:
			('-' = no state change, 'x' = should never occur, '!' = should be 
			prevented at the parent, '?' = need to consult children)
			                      child
				        unsel  sel    selch  selpar excl   exclch
			    unsel     -      !    unsel    x      -    unsel
			    sel     selch    -      -    selch    -    selch 
			par selch   selch    -      -    selch    -    selch 
			    selpar    x      x unsl?selpr  x      x      x
			    excl    exlch    !    exlch    !      -      -
			    exclch  exlch    -    exlch    !      -      -
			"""
			#if parentpath == '/data':
			#	print "/data pstate = %d" % parentstate
			#	print "  %s = %d" % (path, state)
			if state == CheckboxState.UNSELECTED: 
				if parentstate == CheckboxState.SELECTED or \
						parentstate == CheckboxState.SELECTEDCHILD:
					newstate = CheckboxState.SELECTEDCHILD
				elif parentstate == CheckboxState.EXCLUDED or \
						parentstate == CheckboxState.EXCLUDEDCHILD:
					newstate = CheckboxState.EXCLUDEDCHILD
			elif state == CheckboxState.SELECTEDCHILD:
				if parentstate == CheckboxState.UNSELECTED:
					newstate = CheckboxState.UNSELECTED
				elif parentstate == CheckboxState.SELECTEDPARENT:
					if self.checkChildrenStates(child, [CheckboxState.SELECTED, 
							CheckboxState.SELECTEDPARENT]):
						# XXX: did we need to pass in selections to checkChldSt
						newstate = CheckboxState.SELECTEDPARENT
					else:
						newstate = CheckboxState.UNSELECTED
				elif parentstate == CheckboxState.EXCLUDED or \
						parentstate == CheckboxState.EXCLUDEDCHILD:
					newstate = CheckboxState.EXCLUDEDCHILD
			elif state == CheckboxState.SELECTEDPARENT:
				if parentstate == CheckboxState.SELECTED or \
						parentstate == CheckboxState.SELECTEDCHILD:
					newstate = CheckboxState.SELECTEDCHILD
			elif state == CheckboxState.EXCLUDEDCHILD:
				if parentstate == CheckboxState.UNSELECTED:
					newstate = CheckboxState.UNSELECTED
				elif parentstate == CheckboxState.SELECTED or \
						parentstate == CheckboxState.SELECTEDCHILD:
					newstate = CheckboxState.SELECTEDCHILD
			imageidx += CheckboxState.offset(state, newstate)
			self.SetPyData(child, (path, isDir, expanded, newstate))
			self.SetItemImage(child, imageidx) 
			if recurse:
				self.renderChildren(child, recurse)
				# XXX: why do we renderParents here?  It hits the same
				# 'parent's over and over and over again.  If we want to do
				# this, we need to 'collect up' the parents and just call once
				# -- this kills performance.
				#print "renderParents(%s)" % path
				#self.renderParents(child)


	def getChildren(self, node, recurse=False):
		result = []
		child, cookie = self.GetFirstChild(node)
		while child:
			result.append(child)
			if recurse:
				result.extend(self.getChildren(child, recurse))
			child, cookie = self.GetNextChild(node, cookie)
		return result

	def checkChildrenStates(self, node, states, ignorelist=[]):
		children = self.getChildren(node)
		for child in children:
			if child not in ignorelist:
				(p, d, e, childstate) = self.GetItemData(child).GetData()
				for state in states:
					if state == childstate:
						#print "%s has state %d" % (p, state)
						return True
			if self.checkChildrenStates(child, states, ignorelist):
				# do this even if it is in ignorelist, because it may have
				# children which are not in the ignorelist
				return True
		return False

	def getTooltip(self, item):
		text = self.GetItemText(item)
		(path, isDir, expanded, state) = self.GetItemData(item).GetData()
		if state == CheckboxState.SELECTED:
			if isDir:
				text = "'%s' is SELECTED for backup\n" \
						"ALL files within this folder will be backed up\n" \
						"(except those explicitly marked for exclusion)" % text
			else:
				text = "'%s' is SELECTED for backup" % text
		elif state == CheckboxState.UNSELECTED:
			text = "'%s' is NOT selected for backup" % text
		elif state == CheckboxState.SELECTEDPARENT:
			text = "some files within '%s' are selected for backup" % text
		elif state == CheckboxState.SELECTEDCHILD:
			text = "'%s' will be backed up\n" \
					"(one of its parent folders is selected)" % text
		elif state == CheckboxState.EXCLUDED:
			if isDir:
				text = "'%s' is EXCLUDED from backup\n" \
						"No files within this folder will be backed up" % text
			else:
				text = "'%s' is EXCLUDED from backup" % text
		elif state == CheckboxState.EXCLUDEDCHILD:
			text = "'%s' is EXCLUDED from backup\n" \
					"(one of its parent folders is EXCLUDED)" % text
		return text

	def onTooltip(self, event):
		item = event.GetItem()
		text = self.getTooltip(item)
		if text:
			event.SetToolTip(text)
		else:
			event.StopPropagation()
		#print dir(event)

	def onClick(self, event):
		point = (event.GetX(), event.GetY())
		item, flags = self.HitTest(point)
		if flags & wx.TREE_HITTEST_ONITEMICON:
			selections = self.GetSelections()
			self.changeState(item, selections)

	def changeState(self, item, selections=[]):
		(path, isDir, expanded, state) = self.GetItemData(item).GetData()
		if item == self.rootID:
			parent = None
			parentstate = CheckboxState.UNSELECTED
		else:
			parent = self.GetItemParent(item)
			(parentpath, parentisDir, parentexpanded, 
					parentstate) = self.GetItemData(parent).GetData()
		imageidx = self.GetItemImage(item)
		# determine newstate from existing state, parent state, and state 
		# of children
		"""
		Here are the state transitions for the item based on current
		states and parent states: ('-' = no state change, 'x' = should
		never occur, '?' = depends on children state)
							  item
					unsel  sel       selch  selpar excl   exclch
			unsel    sel   excl      sel    sel    unsel  excl
			sel      sel excl?selpar sel      x    selch  excl
		par selch     x    excl      sel    sel    selch  excl
			selpar   sel   excl        x    sel    unsel  excl
			excl      x    excl        x    exclch exclch excl
			exclch    x    excl        x    exclch exclch excl
		"""
		
		newstate = state
		if state == CheckboxState.UNSELECTED:
			newstate = CheckboxState.SELECTED
		elif state == CheckboxState.SELECTEDCHILD:
			newstate = CheckboxState.SELECTED
		elif state == CheckboxState.SELECTEDPARENT:
			if parentstate == CheckboxState.EXCLUDED or \
					parentstate == CheckboxState.EXCLUDEDCHILD:
				# XXX: this should be impossible to reach...
				newstate = CheckboxState.EXCLUDEDCHILD
			else:
				newstate = CheckboxState.SELECTED
		elif state == CheckboxState.SELECTED:
			if self.checkChildrenStates(item, [CheckboxState.SELECTED, 
					CheckboxState.SELECTEDPARENT], selections):
				newstate = CheckboxState.SELECTEDPARENT
			elif self.allowExclude:
				newstate = CheckboxState.EXCLUDED
			else:
				if parent in selections or \
						(parentstate == CheckboxState.UNSELECTED or \
						parentstate == CheckboxState.SELECTEDPARENT):
					newstate = CheckboxState.UNSELECTED
				elif parentstate == CheckboxState.SELECTED or \
						parentstate == CheckboxState.SELECTEDCHILD:
					newstate = CheckboxState.SELECTEDCHILD
		elif state == CheckboxState.EXCLUDED:
			if parent in selections or \
					(parentstate == CheckboxState.UNSELECTED or \
					parentstate == CheckboxState.SELECTEDPARENT):
				newstate = CheckboxState.UNSELECTED
			elif parentstate == CheckboxState.SELECTED or \
					parentstate == CheckboxState.SELECTEDCHILD:
				newstate = CheckboxState.SELECTEDCHILD
			else:
				newstate = CheckboxState.EXCLUDEDCHILD
		elif state == CheckboxState.EXCLUDEDCHILD:
			newstate = CheckboxState.EXCLUDED
		
		if len(selections) > 1:
			# if we have multiple selections, the idea is to move all the
			# selections to the newstate defined above, or to valid 
			# unselected or inherited states if the move to newstate would
			# be invalid.
			"""
			Here are the state transitions for the item based on the
			newstate as determined by the clicked item and the current
			states: ('-' = no state change, '?' = consult children)
										  item
							 unsel  sel     selch  selpar excl   exclch
					 unsel     -    unsel     -      -    unsel    - 
					 sel      sel    -       sel    sel    sel     - 
			newstate selch     -    unsel     -      -    unsel    - 
					 selpar    -    unsel     -      -    unsel    - 
					 excl     excl excl?slpr excl   excl    -     excl 
					 exclch    -    unsel     -      -    unsel    - 
			"""
			for i in selections:
				(mpath, misDir, mexpanded, mstate) = self.GetItemData(
						i).GetData()
				mnewstate = mstate
				if mstate == CheckboxState.UNSELECTED or \
						mstate == CheckboxState.SELECTEDCHILD or \
						mstate == CheckboxState.SELECTEDPARENT:
					if newstate == CheckboxState.SELECTED or \
							newstate == CheckboxState.EXCLUDED:
						mnewstate = newstate
				elif mstate == CheckboxState.SELECTED:
					if newstate == CheckboxState.UNSELECTED or \
							newstate == CheckboxState.SELECTEDCHILD or \
							newstate == CheckboxState.SELECTEDPARENT or \
							newstate == CheckboxState.EXCLUDEDCHILD:
						mnewstate = CheckboxState.UNSELECTED
					elif newstate == CheckboxState.EXCLUDED:
						if self.checkChildrenStates(i, 
								[CheckboxState.SELECTED,
								CheckboxState.SELECTEDPARENT], selections):
							mnewstate = CheckboxState.SELECTEDPARENT
						else:
							mnewstate = newstate
				elif mstate == CheckboxState.EXCLUDED:
					if newstate == CheckboxState.UNSELECTED or \
							newstate == CheckboxState.SELECTEDCHILD or \
							newstate == CheckboxState.SELECTEDPARENT or \
							newstate == CheckboxState.EXCLUDEDCHILD:
						mnewstate = CheckboxState.UNSELECTED
					elif newstate == CheckboxState.SELECTED:
						mnewstate = newstate
				elif mstate == CheckboxState.EXCLUDEDCHILD:
					if newstate == CheckboxState.EXCLUDED:
						mnewstate = newstate 
				self.setItemState(i, mnewstate)
		self.setItemState(item, newstate, (path, isDir, expanded, state, 
			imageidx))
	
	def setItemState(self, item, newstate, oldData=None):
		if oldData:
			(path, isDir, expanded, state, imageidx) = oldData 
		else:
			(path, isDir, expanded, state) = self.GetItemData(item).GetData()
			imageidx = self.GetItemImage(item)
		imageidx += CheckboxState.offset(state, newstate)
		self.SetPyData(item, (path, isDir, expanded, newstate))
		self.SetItemImage(item, imageidx) 
		self.renderChildren(item, True)
		self.renderParents(item)

	def getTopLevelDrives(self):
		sys = platform.system()
		if sys == 'Windows':
			# XXX: need to test this all out
			import win32api, string
			drives = win32api.GetLogicalDriveStrings()
			driveletters = string.splitfields(drives,'\000')
			for d in driveletters:
				type = win32api.GetDriveType("%s:\\" % d)
				# XXX: set the appropriate icon
			return driveletters
		else: # Unix, OSX, etc.
			return ['/']

	def addListener(self, callback):
		self.listeners.append(callback)
	
	def SetPyData(self, item, data):
		wx.TreeCtrl.SetPyData(self, item, data)
		for f in self.listeners:
			f(item, data)

	
			
"""
Tests for DirCheckboxCtrl

A number of unit tests must be performed on the DirCheckboxGUI widget when
refactoring.  Add to this list so that it becomes comprehensive.

Basic Tests:

1. Click on a top-level UNSELECTED object in the tree [should become SELECTED].
   - Click again [should become EXCLUDED].  
   - Click again [should become UNSELECTED].

2. Click on a non-top-level UNSELECTED object in the tree that has no SELECTED
children [should become SELECTED, it's parents should become SELECTEDPARENT and
its children SELECTEDCHILD].
   - Click again [should become EXCLUDED, it's parents who were SELECTEDPARENT
	 should become UNSELECTED, and it's UNSELECTED children should become
	 EXCLUDED].  
   - Click again [should become UNSELECTED, and it's children should become
	 UNSELECTED].

3. Change two children to their SELECTED state [parents should be in
SELECTEDPARENT state].
   - Click one child to become EXCLUDED [parents should stay in SELECTEDPARENT]
   - Click the same child to become UNSELECTED [parents should stay in
	 SELECTEDPARENT]
   - Click the other child to become EXCLUDED [parents should become
	 UNSELECTED]
 
4. Choose a folder and a child item.
   - Click the child to become SEL [parent should be SELPAR]
   - Click the parent [parent should become SEL]
   - Click the parent again [parent should become SELPAR]
 
5. Choose a folder and a child item.
   - Click the parent to become SEL [child should become SELCHILD]
   - Click the child [child should become SEL]
   - Click the child again [child should become EXCL]
   - Click the child again [child should become SELCHILD]
 
6. Pick a node with children at least two-deep.  Change two of the
at-least-two-deep children to their SELECTED state [parents should be in
SELECTEDPARENT state].
   - Click parent closest to SELECTED children to SELECTED [two childen remain
	 in SELECTED, all other children become SELECTEDCHILD.  Parent[s] of parent
	 remain SELECTEDPARENT]
   - Click one child twice to become SELECTEDCHILD [child should not be able to
	 be UNSELECTED, parent states should not change]
   - Click other child twice to become SELECTEDCHILD [child should not be able
	 to be UNSELECTED, parent states should not change]

7. Pick a node with children at least two-deep. 
   - Click deepest parent to SELECTED [Parent[s] of parent become
	 SELECTEDPARENT]
   - Click same parent again to become EXCLUDED [Parent[s] of parent become
	 UNSELECTED]
   - Click same parent again to become UNSELECTED [Parent[s] of parent remain
	 UNSELECTED] 

8. Pick a node with children at least two-deep. 
   - Click deepest child to become SELECTED [Parent[s] of parent become
	 SELECTEDPARENT]
   - Click the topmost parent to become SELECTED [children become
	 SELECTEDCHILD]
   - Click the topmost parent again to become SELECTEDPARENT [middle child
	 should become SELECTEDPARENT]

Multi-Selection Tests:

1. Multi-select three items at the same level and in the same state.  Toggle
between the three main states [SELECTED, EXCLUDED, UNSELECTED]

2. Multi-select three items at the same level, one in each of the three states
(SEL, EXCL, UNSEL).  Toggle the SEL item to see that all three items become
EXCL.

3. Multi-select three items at the same level, one in each of the three states
(SEL, EXCL, UNSEL).  Toggle the EXCL item to see that all three items become
UNSEL.

4. Multi-select three items at the same level, one in each of the three states
(SEL, EXCL, UNSEL).  Toggle the UNSEL item to see that all three items become
SEL.

5. Choose three items that are nested within each other: a parent folder, one
of its children folders, and a file/folder in the child folder.  Choose one
other item from the child folder.
   - set the top parent to UNSEL
   - set the child folder to SEL [parent become SELPAR]
   - set the child item to SEL
   - set the other item to EXCL
   - multi-select all four items
	 - 5A. click on the top parent (which was in SELPAR) [All four items should
	   become SEL, all children of any of these items should become SELCHILD].
	   Toggle twice more [all selected items should toggle to EXCL, then to
	   UNSEL]
	 - 5B. reset as above, click on the child folder [All four items should
	   become EXCL].  Toggle twice more [all selected items should go to UNSEL,
	   then SEL]
	 - 5C. reset as above, click on the child item [All four items should
	   become EXCL].  Toggle twice more [all selected items should go to UNSEL,
	   then SEL]
	 - 5D. reset as above, click on the other item [All four items should
	   become UNSEL].  Toggle twice more [all selected items should go to SEL,
	   then EXCL]

6. Choose a folder, one if its subfolders, a subfolder of the subfolder, and an item in the deepest subfolder, and an item in the first subfolder, e.g.:
	[] A
	  [] B
	    [] C
		  [] D
        [] E
	- change item 'D' to SEL [parents 'A', 'B', and 'C' should go to SELPAR]
	- change item 'E' to EXCL
	- multi-select 'A', 'C', and 'E'
	- toggle 'E' to UNSEL [all other selections should stay in current state]
	- toggle 'E' to SEL ['A' and 'B' become SEL, their children become SELCHILD]
	- toggle 'E' back to EXCL [should get our original multi-select setup back]
	- toggle 'C' to SEL [all selections to SEL, children to SELCHILD]
	- toggle 'C' to SELPAR ['A' and 'C' to SELPAR, 'E' to UNSEL]
	- toggle 'E' twice [should get our original mulit-select setup back]
	
"""

class CheckFileListCtrlMixin:
	# for some insane reason, we can't get EVT_LEFT_DOWN (or _UP) to bind in
	# FileListCtrl itself.  But we are sneaky and can do it by lots of clever
	# hax0ry, like by using this silly mixin.
	def __init__(self, toCall):
		self.Bind(wx.EVT_LEFT_UP, toCall)

class FileListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin, 
		CheckFileListCtrlMixin):
	"""
	Implements a file list control, with a peerctrl that contains the
	filesystem model.  Currently, this peerctrl must implement an addListener(),
	changeState(), GetItemData(), expandDir(), GetSelections(), and
	GetChildren() API similar to that implemented by DirCheckBoxCtrl.
	"""
	def __init__(self, parent, peerctrl, id=-1, pos=wx.DefaultPosition, 
			size=wx.DefaultSize, style=wx.LC_REPORT, 
			validator=wx.DefaultValidator, name=wx.ListCtrlNameStr):

		wx.ListCtrl.__init__(self, parent, id, pos, size, style, validator,
				name)
		CheckFileListCtrlMixin.__init__(self, self.OnClick)
		listmix.ListCtrlAutoWidthMixin.__init__(self)

		self.peerctrl = peerctrl
		self.peerctrl.addListener(self.itemChanged)

		self.itemdict = {} # a dict with filepath as key, containing tuples of
		                   # (index into ListCtrl, reference to peerctrl object)
		self.stopsearch = False

		self.il, self.checkboxes, self.icondict = createDefaultImageList()
		self.AssignImageList(self.il, wx.IMAGE_LIST_SMALL)
		self.il = self.GetImageList(wx.IMAGE_LIST_SMALL)

		self.InsertColumn(0, "Filename")
		self.InsertColumn(1, "Location")
		#self.InsertColumn(2, "Last Backup")

		#self.SetColumnWidth(0, wx.LIST_AUTOSIZE)
		#self.SetColumnWidth(1, -1) #wx.LIST_AUTOSIZE)
		self.Bind(wx.EVT_MOTION, self.mouseMotion)

	def itemChanged(self, item, data):
		(path, isDir, expanded, state) = data
		if self.itemdict.has_key(path):
			item = self.itemdict[path][0]
			image = getFileIcon(path, self.il, self.checkboxes,
					self.icondict) + state
			self.SetItemImage(item, image)

	def GetAll(self, excludeStates=[]):
		result = []
		start = -1
		for i in range(self.GetItemCount()):
			item = self.GetNextItem(start, wx.LIST_NEXT_ALL) 
			# XXX: only append if not in excludeStates
			result.append(item)
			start = item
		return result

	def GetSelections(self):
		result = []
		start = -1
		for i in range(self.GetSelectedItemCount()):
			item = self.GetNextItem(start, wx.LIST_NEXT_ALL, 
					wx.LIST_STATE_SELECTED)
			result.append(item)
			start = item
		return result

	def GetPeerSelections(self, selections):
		result = []
		for item in selections:
			path = os.path.join(self.GetItem(item,1).GetText(), 
					self.GetItemText(item))
			if self.itemdict.has_key(path):
				result.append(self.itemdict[path][1])
		return result

	def mouseMotion(self, event):
		point = event.GetPosition()
		item, flags = self.HitTest(point)
		if flags == wx.LIST_HITTEST_ONITEMICON:
			path = os.path.join(self.GetItem(item,1).GetText(), 
					self.GetItemText(item))
			text = self.peerctrl.getTooltip(self.itemdict[path][1])
			tip = wx.ToolTip(text)
			self.SetToolTip(tip)
			#tipwin = tip.GetWindow()
			#tippos = tipwin.GetPosition()
			#print "%s vs %s" % (tippos, point)
			#tipwin.SetPosition(point)

	def OnClick(self, event):
		point = event.GetPosition()
		item, flags = self.HitTest(point)
		if flags == wx.LIST_HITTEST_ONITEMICON:
			peerselections = self.GetPeerSelections(self.GetSelections())
			path = os.path.join(self.GetItem(item,1).GetText(), 
					self.GetItemText(item))
			ditem = self.itemdict[path][1] # raises if not present
			self.peerctrl.changeState(ditem, peerselections)
			(path, isDir, expanded, state) \
					= self.peerctrl.GetItemData(ditem).GetData()
			image = getFileIcon(path, self.il, self.checkboxes, 
					self.icondict) + state
			self.SetItemImage(item, image)

	def searchButtonAction(self, event):
		selections = self.peerctrl.GetSelections()
		if len(selections) == 0:
			return ("Please tell me where to search.  Select one or more"
					" folders in the left-hand panel (hold down SHIFT or"
					" CTRL for multiple selection), then click the search"
					" button again.", None)
		else:
			self.DeleteAllItems()
			self.itemdict = {}
			b = wx.BusyCursor()
			searchSourceItems = []
			for i in selections:
				self.addResults(i, event.searchstring)
				searchSourceItems.append(i)
			self.searchSourceItems = [self.peerctrl.GetItemData(s).GetData()[0]
					for s in searchSourceItems]
			print "sources: %s" % self.searchSourceItems
		return (None, None)

	def addResults(self, ditem, searchstring):
		(path, isDir, expanded, state) \
				= self.peerctrl.GetItemData(ditem).GetData()
		position = self.GetItemCount()
		if isDir:
			if not expanded:
				self.peerctrl.expandDir(ditem, busycursor=False)
			children = self.peerctrl.getChildren(ditem)
			for c in children:
				self.addResults(c, searchstring)
				wx.Yield()
				if self.stopsearch:
					break
		else:
			terms = [x for x in searchstring.split(' ') if x != '']
			for term in terms:
				print path
				if path.find(term) > 0:
					image = getFileIcon(path, self.il, self.checkboxes, 
							self.icondict) + state
					dirname, filename = os.path.split(path)
					index = self.InsertImageStringItem(position, filename, 
							image)
					self.SetStringItem(index, 1, dirname)
					self.SetColumnWidth(0, wx.LIST_AUTOSIZE)
					self.itemdict[path] = (index, ditem)
					break

	def setGroup(self, state):
		items = self.GetAll()
		item = items[0]
		peerselections = self.GetPeerSelections(items)
		path = os.path.join(self.GetItem(item,1).GetText(), 
				self.GetItemText(item))
		ditem = self.itemdict[path][1] # raises if not present
		while True:
			# cycle until the items state matches the desired state
			self.peerctrl.changeState(ditem, peerselections) # can be slow
			(path, isDir, expanded, nstate) \
					= self.peerctrl.GetItemData(ditem).GetData()
			if nstate == state:
				break
		image = getFileIcon(path, self.il, self.checkboxes, 
				self.icondict) + state
		self.SetItemImage(item, image)
		return  self.searchSourceItems


class GroupSelectionCheckbox(wx.Panel):
	def __init__(self, parent, id=-1, setGroupState=None):
		wx.Panel.__init__(self, parent, id)
		self.setGroupState = setGroupState

		self.ubm = wx.BitmapFromImage(wx.Image("checkbox-unchecked1.png"))
		self.cbm = wx.BitmapFromImage(wx.Image("checkbox-checked1.png"))
		self.ebm = wx.BitmapFromImage(wx.Image("checkbox-excluded1.png"))
		self.checkboxButton = wx.BitmapButton(self, -1, self.ubm, 
				style=wx.NO_BORDER) 
		self.Bind(wx.EVT_BUTTON, self.onCheckbox, self.checkboxButton)
		self.description = wx.StaticText(self, -1, 
				"always BACKUP any files that match these search criteria    ")
		self.state = CheckboxState.UNSELECTED

		self.gbSizer = wx.GridBagSizer(1,2)
		self.gbSizer.Add(self.checkboxButton, (0,0), flag=wx.ALIGN_CENTER)
		self.gbSizer.Add(self.description, (0,1), flag=wx.ALIGN_CENTER)
		self.gbSizer.AddGrowableRow(1)
		self.SetSizerAndFit(self.gbSizer)

	def Enable(self, enable=True):
		self.checkboxButton.Enable(enable)
		self.description.Enable(enable)

	def Disable(self):
		self.Enable(False)

	def clear(self):
		self.checkboxButton.SetBitmapLabel(self.ubm)
		self.state = CheckboxState.UNSELECTED
		self.description.SetLabel(
				"always BACKUP any files that match these search criteria")

	def setState(self, state):
		self.state = state
		if self.state == CheckboxState.UNSELECTED:
			self.checkboxButton.SetBitmapLabel(self.ubm)
			self.description.SetLabel(
					"always BACKUP any files that match these search criteria")
		elif self.state == CheckboxState.SELECTED:
			self.checkboxButton.SetBitmapLabel(self.cbm)
			self.description.SetLabel(
					"always BACKUP any files that match these search criteria")
		elif self.state == CheckboxState.EXCLUDED:
			self.checkboxButton.SetBitmapLabel(self.ebm)
			self.description.SetLabel(
					"always EXCLUDE any files that match these search criteria")

	def onCheckbox(self, event):
		if self.state == CheckboxState.UNSELECTED:
			self.checkboxButton.SetBitmapLabel(self.cbm)
			self.state = CheckboxState.SELECTED
			if self.setGroupState:
				self.setGroupState(CheckboxState.SELECTED)
		elif self.state == CheckboxState.SELECTED:
			self.checkboxButton.SetBitmapLabel(self.ebm)
			self.description.SetLabel(
					"always EXCLUDE any files that match these search criteria")
			self.state = CheckboxState.EXCLUDED
			if self.setGroupState:
				self.setGroupState(CheckboxState.EXCLUDED)
		elif self.state == CheckboxState.EXCLUDED:
			self.checkboxButton.SetBitmapLabel(self.ubm)
			self.description.SetLabel(
					"always BACKUP any files that match these search criteria")
			self.state = CheckboxState.UNSELECTED
			if self.setGroupState:
				self.setGroupState(CheckboxState.UNSELECTED)


class SearchPanel(wx.Panel):
	def __init__(self, parent, dircheckbox, id=-1, searchButtonAction=None):
		wx.Panel.__init__(self, parent, id)
		self.dircheckbox = dircheckbox
		self.searchButtonAction = searchButtonAction

		self.SetAutoLayout(False)
		self.rules = {} # should refer to something from fludrules

		self.searchField = wx.TextCtrl(self, -1, 
				"search for files to backup here", size=wx.Size(-1,-1), 
				style=wx.TE_PROCESS_ENTER)
		self.searchField.SetToolTipString('find files within directories'
				' selected to the left by entering search terms here')
		self.searchField.Bind(wx.EVT_TEXT_ENTER, self.onSearchClick)
		self.searchField.Bind(wx.EVT_COMMAND_LEFT_CLICK, self.selectAllText)

		self.searchButton = wx.Button(self, -1, 'find!', name='searchButton')
		self.Bind(wx.EVT_BUTTON, self.onSearchClick, self.searchButton)

		self.searchResults = FileListCtrl(self, dircheckbox, -1, 
				name='searchResults', style=wx.SUNKEN_BORDER | wx.LC_REPORT)
		self.searchResults.SetExtraStyle(0)
		self.searchResults.SetLabel('found files')

		self.groupSelection = GroupSelectionCheckbox(self, -1, self.setGroup)
		self.groupSelection.Disable()

		self.gbSizer = wx.GridBagSizer(3,2)
		self.gbSizer.Add(self.searchField, (0,0), flag=wx.EXPAND)
		self.gbSizer.Add(self.searchButton, (0,1))
		self.gbSizer.Add(self.searchResults, (1,0), (1,2), 
				flag=wx.EXPAND|wx.TOP, border=5)
		self.gbSizer.Add(self.groupSelection, (2,0) )
		self.gbSizer.AddGrowableRow(1)
		self.gbSizer.AddGrowableCol(0)
		self.SetSizerAndFit(self.gbSizer)

	def onSearchClick(self, event):
		event.searchstring = self.searchField.GetValue()
		if self.searchButton.GetLabel() == 'stop!':
			self.searchButton.SetLabel('find!')
			self.searchResults.stopsearch = True
			return
		else:
			self.groupSelection.clear()
			self.groupSelection.Disable()
			self.searchButton.SetLabel('stop!')
			self.searchButton.Update()
		err, info = self.searchResults.searchButtonAction(event)
		selections = self.searchResults.searchSourceItems

		# see if we should set the checkbox button from a previous rule
		state = None
		if len(selections) > 0 and self.rules.has_key(selections[0]):
			rule = self.rules[selections[0]]
			if self.rules[selections[0]].has_key(event.searchstring):
				state = self.rules[selections[0]][event.searchstring]
			for i in selections:
				if not self.rules.has_key(i) or self.rules[i] != rule:
					state = None
					break
				#for j in self.rules[i]:

		if state:
			print "should restore checkbox to %s" % state
			self.groupSelection.setState(state)

		self.searchButton.SetLabel('find!')
		self.searchResults.stopsearch = False
		if self.searchButtonAction:
			self.searchButtonAction(event, errmsg=err, infomsg=info)
		self.groupSelection.Enable()

	def selectAllText(self, event):
		print "heya"
		self.searchField.SetSelection(-1,-1)

	def setGroup(self, state):
		b = wx.BusyCursor()
		selections = self.searchResults.setGroup(state)	
		for s in selections:
			if not self.rules.has_key(s):
				self.rules[s] = {}
			if state == CheckboxState.UNSELECTED:
				try:
					self.rules.pop(s)
				except:
					pass
			else:
				self.rules[s][self.searchField.GetValue()] = state
		print self.rules

class FilePanel(wx.SplitterWindow):
	def __init__(self, parent, searchButtonAction=None):
		# Use the WANTS_CHARS style so the panel doesn't eat the Return key.
		wx.SplitterWindow.__init__(self, parent, -1, 
				style=wx.SP_LIVE_UPDATE | wx.CLIP_CHILDREN | wx.WANTS_CHARS)
		self.Bind(wx.EVT_SIZE, self.OnSize)
		self.SetNeedUpdating(True)

		self.tree = DirCheckboxCtrl(self, -1, dir="/") 
		
		# XXX: fludrules.init path should be in config
		self.fludrules = self.getFludHome()+"/fludrules.init"
		if not os.path.isfile(self.fludrules):
			# XXX: do the other first time stuff (email encrypted credentials,
			#      etc.)
			parent.SetMessage("Welcome. This appears to be the first"
				" time you've run flud. We've automatically selected some"
				" files for backup.  You can make changes by"
				" selecting/deselecting files and directories. When you are"
				" done, simply close this window.")
			src = open('fludrules.init', 'r')
			dst = open(self.fludrules, 'w')
			filerules = src.read()
			dst.write(filerules)
			dst.close()
			src.close()
			filerules = eval(filerules)
			rulestates = {}
			for rule in filerules['baserules']:
				value = filerules['baserules'][rule]
				rule = glob.glob(os.path.expandvars(rule))
				for r in rule:
					rulestates[r] = value
			self.tree.setStates(rulestates)

		# XXX: fludfile.conf path should be in config
		self.fludfiles = self.getFludHome()+"/fludfile.conf"
		print self.fludfiles
		if os.path.isfile(self.fludfiles):
			file = open(self.fludfiles, 'r')
			states = eval(file.read())
			self.tree.setStates(states)
			file.close()

		self.searchPanel = SearchPanel(self, dircheckbox=self.tree, 
				searchButtonAction=searchButtonAction)

		self.SetMinimumPaneSize(20)
		self.SplitVertically(self.tree, self.searchPanel) #, 300)

	def getFludHome(self):
		if os.environ.has_key('FLUDHOME'):
			fludhome = os.environ['FLUDHOME']
		else:
			fludhome = os.environ['HOME']+"/.flud"
		if not os.path.isdir(fludhome):
			os.mkdir(fludhome, 0700)
		return fludhome	

	def shutdown(self, event):
		states = self.tree.getStates()
		f = open(self.fludfiles, 'w')
		f.write(str(states))
		f.close()
		for i in states:
			# XXX: need to communicate the backup of the indicated files.
			#      perhaps this is done entirely by the file we just saved...
			print "%s %s" % (i, states[i])
		event.Skip()

	def OnSize(self, event):
		w,h = self.GetClientSizeTuple()
		if self.tree:
			self.tree.SetDimensions(0, 0, w, h)
		event.Skip()

class RestoreCheckboxCtrl(DirCheckboxCtrl):
	# XXX: child/parent selection/deselection isn't quite right still, esp wrt
	# root node.  repro:
	# -/
	#   -d1
	#     -f1
	#   -d2
	#     -d3
	#       -f2
	#       -f3
	# with nothing selected, select d3 and f3, then select root, then deselect
	# d3 and f3
	def __init__(self, parent, id=-1, config=None, pos=wx.DefaultPosition,
			size=wx.DefaultSize,
			style=(wx.TR_MULTIPLE 
				| wx.TR_HAS_BUTTONS 
				| wx.TR_TWIST_BUTTONS 
				| wx.TR_NO_LINES 
				| wx.TR_FULL_ROW_HIGHLIGHT
				| wx.SUNKEN_BORDER), 
			validator=wx.DefaultValidator, name=wx.ControlNameStr):
		self.config = config
		DirCheckboxCtrl.__init__(self, parent, id, config, pos, size, style,
				validator, name, allowExclude=False)
	
	def expandRoot(self, config):
		self.defaultImageList, self.checkboxes, self.icondict \
				= createDefaultImageList()
		self.AssignImageList(self.defaultImageList)
		self.il = self.GetImageList()
		self.rootID = self.AddRoot("/", self.icondict['computer'], -1,
				wx.TreeItemData(("", True, False, CheckboxState.UNSELECTED)))
		self.Expand(self.rootID)
		master = listMeta(config)
		for i in master:
			if not isinstance(master[i], dict):
				traversal = i.split(os.path.sep)
				node = self.rootID
				path = "/"
				if traversal[0] == '':
					traversal.remove('')
				for n in traversal:
					path = os.path.join(path, n)
					if n == traversal[-1]:
						child = self.AppendItem(node, n)
						self.SetPyData(child, (path, False, False, 0)) 
						idx = getFileIcon(i, self.il, self.checkboxes, 
								self.icondict)
						self.SetItemImage(child, idx, wx.TreeItemIcon_Normal)
					else:
						children = self.getChildrenDict(node)
						if not n in children:
							child = self.AppendItem(node, n)
							self.SetPyData(child, (path, True, False, 0)) 
							self.SetItemImage(child, self.icondict['folder'],
									wx.TreeItemIcon_Normal)
						else:
							child = children[n]
						node = child

	def getChildrenDict(self, node):
		result = {}
		child, cookie = self.GetFirstChild(node)
		while child:
			result[self.GetItemText(child)] = child
			child, cookie = self.GetNextChild(node, cookie)
		return result

	def onExpand(self, event):
		pass

	def getSelected(self, startNode=None):
		if not startNode:
			startNode = self.rootID
		children = self.getChildren(startNode)
		selected = []
		for n in children:
			(path, isDir, expanded, state) = self.GetItemData(n).GetData()
			if not isDir and self.GetItemTextColour(n) != wx.BLUE \
					and (state == CheckboxState.SELECTED \
					or state == CheckboxState.SELECTEDCHILD):
				selected.append(n)
			if isDir and (state == CheckboxState.SELECTED \
					or state == CheckboxState.SELECTEDPARENT \
					or state == CheckboxState.SELECTEDCHILD):
				selected += self.getSelected(n)
		return selected


class RestorePanel(wx.Panel):
	def __init__(self, parent, config, factory):
		self.config = config
		self.factory = factory

		wx.Panel.__init__(self, parent, -1)
		self.Bind(wx.EVT_SIZE, self.OnSize)

		self.tree = RestoreCheckboxCtrl(self, -1, config, #wx.TreeCtrl(self, -1,
				style=(wx.TR_MULTIPLE
					| wx.TR_HAS_BUTTONS
					| wx.TR_TWIST_BUTTONS
					| wx.TR_NO_LINES
					| wx.TR_FULL_ROW_HIGHLIGHT
					| wx.SUNKEN_BORDER))

		self.restoreButton = wx.Button(self, -1, 'restore selected files', 
				name='restoreButton')
		self.Bind(wx.EVT_BUTTON, self.onRestoreClick, self.restoreButton)

		self.gbSizer = wx.GridBagSizer(2,1)
		self.gbSizer.Add(self.tree, (0,0), flag=wx.EXPAND|wx.ALL, border=0)
		self.gbSizer.Add(self.restoreButton, (1,0), flag=wx.EXPAND|wx.ALL, 
				border=0)
		self.gbSizer.AddGrowableRow(0)
		self.gbSizer.AddGrowableCol(0)
		self.SetSizerAndFit(self.gbSizer)

	def OnSize(self, event):
		w,h = self.GetClientSizeTuple()
		event.Skip()

	def onRestoreClick(self, event):
		for n in self.tree.getSelected():
			(path, isDir, expanded, state) = self.tree.GetItemData(n).GetData()
			print "restoring %s" % path
			d = self.factory.sendGETF(path)
			d.addCallback(self.restored, n)
			d.addErrback(self.restoreFailed, n)

	def restored(self, res, n):
		(path, isDir, expanded, state) = self.tree.GetItemData(n).GetData()
		print "yay, %s" % path
		self.tree.SetItemTextColour(n, wx.BLUE)

	def restoreFailed(self, err, n):
		(path, isDir, expanded, state) = self.tree.GetItemData(n).GetData()
		print "boo, %s: %s" % (path, err)
		self.tree.SetItemTextColour(n, wx.RED)

class SchedulePanel(wx.Panel):
	def __init__(self, parent):
		wx.Panel.__init__(self, parent, -1)
		self.Bind(wx.EVT_SIZE, self.OnSize)

	def OnSize(self, event):
		w,h = self.GetClientSizeTuple()
		event.Skip()

class FeedbackPanel(wx.Panel):
	def __init__(self, parent):
		wx.Panel.__init__(self, parent, -1)
		self.Bind(wx.EVT_SIZE, self.OnSize)
		editor = wx.lib.editor.editor.Editor(parent, -1)

	def OnSize(self, event):
		w,h = self.GetClientSizeTuple()
		event.Skip()


class FludNotebook(wx.Notebook):
	def __init__(self, parent, id=-1, pos=wx.DefaultPosition, 
			size=wx.DefaultSize, style=wx.NB_BOTTOM|wx.NO_BORDER):
		self.parent = parent
		self.config = parent.config

		self.factory = LocalClientFactory(self.config)
		print "connecting to localhost:%d" % config.clientport
		reactor.connectTCP('localhost', config.clientport, self.factory)

		wx.Notebook.__init__(self, parent, id, pos, style=style)
		self.filePanel = FilePanel(self, 
				searchButtonAction=parent.searchButtonAction)
		self.AddPage(self.filePanel, "Select Files")
		self.restorePanel = RestorePanel(self, self.config, self.factory)
		self.AddPage(self.restorePanel, "Restore")
		self.schedulePanel = SchedulePanel(self)
		self.AddPage(self.schedulePanel, "Backup Schedule")
		self.feedbackPanel = FeedbackPanel(self)
		self.AddPage(self.feedbackPanel, "Feedback")

	def shutdown(self, event):
		self.filePanel.shutdown(event)

	def SetMessage(self, msg):
		self.parent.SetMessage(msg)


class FludLogoPanel(wx.Panel):
	def __init__(self, parent, id=-1, pos=wx.DefaultPosition, 
			size=wx.Size(10,10), style=wx.TAB_TRAVERSAL, name="logo panel"):
		wx.Panel.__init__(self, parent, id, pos, size, style, name)
		self.SetAutoLayout(True)
		self.SetBackgroundColour(wx.BLACK)
		self.SetForegroundColour(wx.WHITE)

		logobmp = wx.BitmapFromImage(
				wx.Image("flud-backup-logo-1-150-nodrop.png"))
		pad = 0
		self.logowidth = logobmp.GetWidth()
		self.logoheight = logobmp.GetHeight()
		self.logo = wx.StaticBitmap(self, -1, logobmp)

		self.messagePanel = wx.Panel(self, -1)
		self.messagePanel.SetBackgroundColour(wx.BLACK)
		self.messagePanel.SetForegroundColour(wx.WHITE)
		self.message = wx.StaticText(self.messagePanel, -1,
				"message text area", style=wx.ALIGN_CENTER)
		self.message.Bind(wx.EVT_SIZE, self.resizeMessage)
		self.bsizer = wx.BoxSizer(wx.VERTICAL)
		self.bsizer.Add(self.message, flag=wx.EXPAND|wx.ALL, border=35)
		self.bsizer.SetSizeHints(self.messagePanel)
		self.messagePanel.SetSizer(self.bsizer)

		self.gbSizer = wx.GridBagSizer(1,2)
		self.gbSizer.Add(self.logo, (0,0))
		self.gbSizer.Add(self.messagePanel, (0,1), flag=wx.EXPAND|wx.ALL) 
		self.gbSizer.AddGrowableRow(1)
		self.gbSizer.AddGrowableCol(1)
		self.SetSizerAndFit(self.gbSizer)

		self.SetSize(wx.Size(self.logowidth, self.logoheight))
		self.SetSizeHints(self.logowidth, self.logoheight, -1, self.logoheight)

	def SetMessage(self, msg):
		(w,h) = self.message.GetSizeTuple()
		self.message.SetLabel(msg)
		self.message.Wrap(w) 
		self.message.Center()

	def resizeMessage(self, evt):
		# this is mainly to deal with StaticText wonkiness (not calling Wrap()
		# automatically, not centering properly automatically).  It may be
		# possible to get rid of this with a future wxPython release.
		(w,h) = self.message.GetSizeTuple()
		self.message.Wrap(w) 
		m = self.message.GetLabel()
		m = m.replace('\n',' ')
		self.message.SetLabel(m)
		self.message.Wrap(w) 
		self.message.Center()


class FludFrame(wx.Frame):
	def __init__(self, parent, id=wx.ID_ANY, label="flud bakcup client", 
			size=wx.Size(800,600), 
			style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE,
			config=None):
		wx.Frame.__init__(self, parent, id, label, size=size, style=style)

		wx.ToolTip.SetDelay(2000)

		self.clearMessage = False

		self.logoPanel = FludLogoPanel(self)
		self.SetMessage('Welcome.')

		self.config = config
		self.notebook = FludNotebook(self)

		self.operationStatus = wx.StatusBar(name='operationStatus', 
				parent=self, style=0)
		self.SetStatusBar(self.operationStatus)

		self.gbSizer = wx.GridBagSizer(2,1)
		self.gbSizer.Add(self.logoPanel,(0,0), flag=wx.EXPAND)
		self.gbSizer.Add(self.notebook, (1,0), flag=wx.EXPAND|wx.ALL, border=1)
		self.gbSizer.AddGrowableRow(1)
		self.gbSizer.AddGrowableCol(0)
		self.SetSizerAndFit(self.gbSizer)

		self.Bind(wx.EVT_CLOSE, self.shutdown)
		self.SetSize(size)
		self.Show(True)

	def SetMessage(self, message):
		self.logoPanel.SetMessage(message)

	def shutdown(self, event):
		self.notebook.shutdown(event)
		
	def searchButtonAction(self, event, errmsg=None, infomsg=None):
		if errmsg:
			self.logoPanel.SetMessage(errmsg)
			self.clearMessage = True
		elif infomsg:
			self.logoPanel.SetMessage(infomsg)
			self.clearMessage = False
		elif self.clearMessage:
			self.logoPanel.SetMessage("")
		

if __name__ == '__main__':
	app = wx.PySimpleApp()
	
	config = FludConfig()
	config.load(doLogging=False)

	f = FludFrame(None, wx.ID_ANY, 'flud backup client', size=(800,600),
			style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE,
			config=config)

	from twisted.internet import reactor
	reactor.registerWxApp(app)
	reactor.run()

