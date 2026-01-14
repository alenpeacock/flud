import os, stat, sys, tarfile, tempfile
import gzip

from flud.FludCrypto import hashstream
from flud.fencode import fencode

"""
TarfileUtils.py (c) 2003-2006 Alen Peacock.  This program is distributed under
the terms of the GNU General Public License (the GPL), version 3.

Provides additional tarfile functionality (deletion of a member from a
tarball, and concatenation of tarballs).
"""

def delete(tarball, membernames):
    """
    Deletes a member file[s] from a tarball.  Returns the names of deleted
    members if they are removed, False if the file[s] aren't members.  If
    membernames contains all the members in the tarball, the entire tarball is
    deleted
    """
    gzipped = False
    if tarball[-7:] == ".tar.gz":
        gzipped = True
        f = tarfile.open(tarball, 'r:gz')
    else:
        f = tarfile.open(tarball, 'r')
    if not isinstance(membernames, list):
        membernames = [membernames]
    tarnames = f.getnames()
    for membername in membernames: 
        if not membername in tarnames:
            membernames.remove(membername)
    if len(membernames) < 1:
        f.close()
        return False
    if len(tarnames) == len(membernames):
        f.close()
        os.remove(tarball)
        return True
    f.close()
    if gzipped:
        tarball = gunzipTarball(tarball)
    f = open(tarball, 'rb+')
    tfile = tempfile.mktemp()
    if gzipped:
        f2 = gzip.GzipFile(tfile, 'wb')
    else:
        f2 = open(tfile, 'wb')
    empty = tarfile.BLOCKSIZE * b'\0'
    done = False
    removednames = []
    while not done:
        bytes = f.read(tarfile.BLOCKSIZE)
        if not bytes:
            done = True
        elif bytes == empty:
            f2.write(bytes)
        else:
            name = bytes[0:99]
            name = name[:name.find(b'\0')].decode("utf-8", errors="ignore")
            size = int(bytes[124:135], 8)
            blocks = size // tarfile.BLOCKSIZE
            if (size % tarfile.BLOCKSIZE) > 0:
                blocks += 1
            if name in membernames:
                f.seek(blocks*tarfile.BLOCKSIZE + f.tell())
                removednames.append(name)
            else:
                f2.write(bytes)
                for i in range(blocks):
                    f2.write(f.read(tarfile.BLOCKSIZE))
    f2.close()
    f.close()
    if gzipped:
        os.remove(tarball)
        tarball = tarball+".gz"
    os.rename(tfile, tarball)
    return removednames

def concatenate(tarfile1, tarfile2):
    """
    Combines tarfile1 and tarfile2 into tarfile1.  tarfile1 is modified in the
    process, and tarfile2 is deleted.
    """
    gzipped = False
    if tarfile1[-7:] == ".tar.gz":
        gzipped = True
        tarfile1 = gunzipTarball(tarfile1)

    if tarfile2[-7:] == ".tar.gz":
        t2 = tarfile.open(tarfile2, "r:gz")
    else:
        t2 = tarfile.open(tarfile2, "r")

    t1 = tarfile.open(tarfile1, "a")
    try:
        for member in t2.getmembers():
            fileobj = t2.extractfile(member) if member.isfile() else None
            t1.addfile(member, fileobj)
            if fileobj:
                fileobj.close()
    finally:
        t2.close()
        t1.close()

    if gzipped:
        tarfile1 = gzipTarball(tarfile1)

    os.remove(tarfile2)

def verifyHashes(tarball, ignoreExt=None):
    # return all the names of files in this tarball if hash checksum passes,
    # otherwise return False
    digests = []
    if tarball[-7:] == ".tar.gz":
        tar = tarfile.open(tarball, "r:gz")
    else:
        tar = tarfile.open(tarball, "r")
    if ignoreExt and not isinstance(ignoreExt, str):
        ignore_names = set(ignoreExt)
    elif ignoreExt:
        ignore_names = {ignoreExt}
    else:
        ignore_names = set()
    try:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = member.name
            if name.endswith(".meta"):
                continue
            if name in ignore_names:
                continue
            f = tar.extractfile(member)
            if f is None:
                tar.close()
                return []
            digest = hashstream(f, member.size)
            f.close()
            digest = fencode(int(digest, 16))
            if name == digest:
                digests.append(name)
            else:
                tar.close()
                return []
    finally:
        tar.close()
    return digests

def gzipTarball(tarball):
    if tarball[-4:] != '.tar':
        return None
    f = gzip.GzipFile(tarball+".gz", 'wb')
    with open(tarball, 'rb') as fsrc:
        f.write(fsrc.read())
    f.close()
    os.remove(tarball)
    return tarball+".gz"

def gunzipTarball(tarball):
    if tarball[-3:] != '.gz':
        return None
    f = gzip.GzipFile(tarball, 'rb')
    with open(tarball[:-3], 'wb') as f_out:
        f_out.write(f.read())
    f.close()
    os.remove(tarball)
    return tarball[:-3]

if __name__ == "__main__":
    if (len(sys.argv) < 4 or sys.argv[1] != "-d") \
            and (len(sys.argv) != 4 or sys.argv[1] != "-c") \
            and sys.argv[1] != "-v":
        print("usage: [-d tarfile tarfilemembers]\n"\
                +"       [-c tarfile1 tarfile2]\n"\
                +"       [-v tarfile]\n"\
                +" -d deletes tarfilemembers from tarfile,\n"\
                +" -c concatenates tarfile1 and tarfile2 into tarfile1\n"\
                +" -v verifies that the names of files in tarfile are sha256\n")
        sys.exit(-1)
    if sys.argv[1] == "-d":
        deleted = delete(sys.argv[2], sys.argv[3:])
        if deleted == sys.argv[3:]:
            print("%s successfully deleted from %s" % (deleted, sys.argv[2]))
        else:
            faileddeletes = [x for x in sys.argv[3:] if x not in deleted]
            print("could not delete %s from %s" % (faileddeletes, sys.argv[2]))
    elif sys.argv[1] == "-c":
        concatenate(sys.argv[2], sys.argv[3])
        print("concatenated %s and %s into %s" % (sys.argv[2], sys.argv[3],
                sys.argv[2]))
    elif sys.argv[1] == "-v":
        digests = verifyHashes(sys.argv[2])
        if digests:
            print("verified tarfile member digests for: %s" % digests)
        else:
            print("some tarfile members failed digest check")
