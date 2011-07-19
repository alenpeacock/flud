import os, __builtin__, tempfile, stat, sys, struct
from binascii import crc32

sys.path.append("..")
from flud.fencode import fencode, fdecode

"""
BlockFile.py (c) 2003-2006 Alen Peacock.  This program is distributed under the
terms of the GNU General Public License (the GPL), version 3.

Implements accounting information for block data.  The interface for BlockFiles
matches that of normal file objects (read, seek, write, tell, close).  A
BlockFile is generated by calling BlockFile.open() instead of the regular
open().  Additional methods are available for reading and updating the
accounting information.

Currently, the accounting information is stored in-file with the
block data, with a simple header that gives the data's real length, and then
after that the list of originating nodes, fencoded (but these details are meant
to be hidden, so that we can change this in the future, by, for example, using
a proper DB or managing seperate per-node lists as their own files).
"""

def open(fname, mode='rb+'):
    """ Return a BlockFile object. """
    return BlockFile(fname, mode)

def convert(fname, nodeIDandMeta=None):
    """
    Convert a non-BlockFile to a BlockFile, with an optional nodeID/metadata
    pair to add.  The file represented by fname will be a BlockFile upon
    successful return.
    nodeIdAndMeta should be a tuple.  The first element is the nodeID, the
    second the metadata.  Metadata should be a dict (client can send arbitrary
    dict, but the purpose is to have a key/value pair where the key is the
    crc32 checksum of the full metadata, and the value is the chunk of metadata
    being stored with this BlockFile)
    """
    tname = tempfile.mktemp()
    f1 = __builtin__.open(fname, 'rb')
    f2 = __builtin__.open(tname, 'wb')
    size = os.stat(fname)[stat.ST_SIZE]
    f2.write(struct.pack('=Q',size))
    while 1:
        buf = f1.read()
        if buf == "":
            break
        f2.write(buf)
    if nodeIDandMeta == None:
        l = {} 
    else:
        if len(nodeIDandMeta) != 2:
            raise IOError("invalid nodeID/metadata pair")
        nodeID = nodeIDandMeta[0]
        meta = nodeIDandMeta[1]
        if not isinstance(meta, dict):
            raise IOError("invalid metadata (should be a dict)")
        l = {} 
        l[nodeID] = meta
    f2.write(fencode(l))
    f2.close()
    f1.close()
    os.rename(tname, fname)

class BlockFile:
    """
    >>> fname = tempfile.mktemp()
    >>> fdata = 'aaaaaaaaaaaaaaaabbbbbbbbbbbbbbbbadfaf123456789'
    >>> otherdata = '_AAAAAAAA_'
    >>> f1 = __builtin__.open(fname,'wb')
    >>> f1.write(fdata)
    >>> f1.close()
    >>> convert(fname, (1234567890, {1: 'x'}))
    >>> f = open(fname)
    >>> f.hasNode(1234567890)
    True
    >>> f.meta(1234567890) 
    {1: 'x'}
    >>> f.addNode(7)
    >>> f.addNode(8, {10: 12})
    >>> f.addNode(9, {'ff': 'y'})
    >>> f.addNode(9, {'gg': 'z'})
    >>> f.close()
    >>> f = open(fname)
    >>> f.hasNode(7)
    True
    >>> f.meta(7) == None
    True
    >>> f.addNode(7, {1: 2})
    >>> f.meta(7)
    {1: 2}
    >>> f.hasNode(8)
    True
    >>> f.meta(8)
    {10: 12}
    >>> f.hasNode(9)
    True
    >>> f.meta(9)
    {'gg': 'z', 'ff': 'y'}
    >>> f.addNode(9, {'gg': 'x'})
    >>> f.meta(9)
    {'gg': 'x', 'ff': 'y'}
    >>> f.hasNode(34)
    False
    >>> f.meta(34)
    False
    >>> f.hasNode(1234567890)
    True
    >>> f.delNode(7)
    >>> f.close()
    >>> f = open(fname)
    >>> f.hasNode(7)
    False
    >>> f.read() == fdata
    True
    >>> f.write(otherdata)
    >>> f.close()
    >>> f = open(fname)
    >>> f.hasNode(1234567890)
    True
    >>> f.read() == fdata+otherdata
    True
    >>> overlap = len(otherdata) / 2
    >>> f.seek(len(fdata)+len(otherdata)-overlap)
    >>> f.write(otherdata)
    >>> f.close()
    >>> f = open(fname)
    >>> f.read() == fdata+otherdata[:-overlap]+otherdata
    True
    >>> f.hasNode(1234567890)
    True
    >>> f.close()
    >>> f = open(fname)
    >>> f.delNode(9, 'gg')
    >>> f.hasNode(9)
    True
    >>> f.meta(9)
    {'ff': 'y'}
    >>> f.delNode(9, 'ff')
    >>> f.hasNode(9)
    False
    >>> f.addNode(9, {'ff': 'y'})
    >>> f.addNode(9, {'gg': 'z'})
    >>> f.hasNode(9)
    True
    >>> f.delNode(9)
    >>> f.hasNode(9)
    False
    >>> os.remove(fname)
    """

    def __init__(self, fname, mode):
        # XXX: need to check fname and throw if it isn't a proper BlockFile
        self._fname = fname
        self.mode = mode
        self._file = __builtin__.open(fname, mode)
        sizeString = self._file.read(8)
        self._size = struct.unpack('=Q',sizeString)[0]
        self._dataend = 8 + self._size
        self._file.seek(self._dataend)
        self._accounting = fdecode(self._file.read())
        self._accountingcrc = crc32(str(self._accounting))
        self._changed = False
        if mode[0] == 'a':
            self._file.seek(self._dataend)
        else:
            self._file.seek(8) 
    
    def __del__(self):
        self.close()
        
    def read(self, len=None):
        if len == None:
            len = self._dataend - self._file.tell()
        else:
            if self._file.tell()+len > self._dataend:
                len = self._dataend - self._file.tell()
            if len <= 0:
                return ""
        return self._file.read(len)

    def seek(self, pos):
        if pos < 0:
            pos = 0
        if pos > self._dataend-8:
            pos = self._dataend-8
        self._file.seek(8+pos)

    def tell(self):
        return self._file.tell() - 8

    def size(self):
        # returns the 'true' size of the file (not including BlockFile
        # accounting data)
        return self._size

    def write(self, data):
        self._changed = True
        self._file.write(data)
        if self._file.tell() > self._dataend:
            enlargement = self._file.tell() - self._dataend
            self._dataend = self._file.tell()
            self._size = self._size + enlargement
            self._file.seek(0)
            self._file.write(struct.pack("=Q",self._size))
            self._file.seek(self._dataend)

    def close(self):
        if not self._file.closed: # XXX
            if (self.mode[0] != 'r' or self.mode.find('+') > 0) \
                    and (self._changed 
                        or crc32(str(self._accounting)) != self._accountingcrc):
                saved = self._file.tell()
                self._file.seek(self._dataend)
                self._file.write(fencode(self._accounting))
                self._file.truncate()
                self._file.seek(saved)
            self._file.close()

    def addNode(self, nodeID, meta=None):
        if self.mode[0] == 'r' and self.mode.find('+') < 0:
            raise IOError("cannot add a node to a read-only BlockFile")
        if meta is None:
            self._accounting[nodeID] = meta
            return
        if not isinstance(meta, dict):
            raise IOError("invalid metadata (should be a dict)")
        if not nodeID in self._accounting or self._accounting[nodeID] == None:
            self._accounting[nodeID] = meta
        else:
            for key in meta:
                self._accounting[nodeID][key] = meta[key]
    
    def hasNode(self, nodeID):
        return nodeID in self._accounting

    def meta(self, nodeID):
        if nodeID not in self._accounting:
            return False
        else:
            #return self._accounting
            return self._accounting[nodeID]

    def delNode(self, nodeID, metakey=None):
        if self.mode[0] == 'r' and self.mode.find('+') < 0:
            raise IOError("cannot delete a node from a read-only BlockFile")
        if nodeID in self._accounting:
            m = self._accounting[nodeID]
            if not metakey:
                m = {}
            elif metakey in m:
                m.pop(metakey)
            if m:
                self._accounting[nodeID] = m
            else:
                self._accounting.pop(nodeID)

    def getNodes(self):
        return self._accounting

    def emptyNodes(self):
        return (len(self._accounting) == 0)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
