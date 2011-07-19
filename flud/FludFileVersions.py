
"""
Okay, so this isn't a real python module, yet.  Wanted to get down a few ideas
on versioning.  First, the background. 

Traditional backup systems that provide versioning support allow the user to
retrieve the current version of a file, or any of N previous versions that were
stored during previous backup operations.  Since it was rather trivial to
simply keep old versions on the central backup server, this wasn't much of an
engineering problem (at worst, disk fills up quickly).

With a collaborative backup system, such a scheme is less practical.  If fully
enabled, it can consume many times the storage space of a simple
single-snapshot system.  If you want to enforce fairness, you must require
that the number of resources you consume are proportional to those that you
provide.  Encoding already dictates that this ratio is imbalanced towards 
providing more resources than consuming.  But "server-side" versioning, even
when using a clever delta-compression technique, really tips the scales.

There is good news, however.  We can use a single-snapshot system to provide
versioning by requiring all versioning to occur locally.  That is, the 
consumer's own hard drive can be used to maintain multiple versions of files,
and then the whole thing can be backed up as a single-snapshot to the flud 
network.  Think of a local CVS repository (with many versions contained
therein) that is set to be backed up; the backup system doesn't have to worry
about versioning -- it just backs up the current data.  The local CVS repo
is in charge of worrying about versions.  To the user, its all the same.

The advantages of this scheme are mainly:
    1) simplicity
    2) storage consumption minimization, opt-in
    3) decoupling of versioning layer from backup layer

Of the three, #1 is really the most appealing.  We just back up the current
view.  This also greatly simplifies the verification mechanism -- the verifier
will always have the complete file from which to do challenge/response queries
to the verifiee.  We don't have to worry about keeping deltas or partial
checksums or anything like that in order to do verification;  we just pick a
block of bytes at random from within the file, and make sure that the storer
can return us the hash of those bytes.  #1 also means that we don't have to do
anything complicated to figure out what the delta of a delta-compressed version
should be (i.e., we don't need to request the old version from the storage
system, compare it with our version, then send out a delta) -- in fact, with
this scheme we wipe out delta compression altogether, at least from the
viewpoint of the storage mechanism (some other local mechanism is welcome to
use delta compression to store versions locally, but this mechanism won't need
to download lots of data in order to do so, because it will all be local).

#2 is nice.  It means that if the user isn't interested in versioning, they
don't have to do it.  This will be the default, in fact.  This means that we
eliminate a lot of overhead that we would have had if every user was storing
versions, even if they didn't need them.  It also means that there is an
automatic cost for enabling versions, not only for the collaborative system,
but for the user's local storage resources.  Not to imply that we want to
punish the user for enabling versions, but there's no free lunch (and besides,
adding local disk is cheap).

  [as an aside, here, versioning does become necessary quite quickly for things
  such as email clients that store all mail in a particular folder as one
  large file, or other applications that use databases in single files -- we
  don't want the user to have to send the whole file (which can become quite
  large) every time they get a new email or change the db slightly.  The good
  news is that we can still provide this in its own layer].

Decoupling (#3) is always a good idea, especially when it can be done cleanly.
The user (or flud client developer) is free to implement whatever local
versioning scheme they want.  They can make copies of files and store them in
other directories, they could use a version control system such as CVS, they
could do their own delta compression and store the deltas in a special
directory.  They could store as many or as few versions as they want.  They can
take version snapshots often or seldom, and this is independent of how often
they perform backup.  And such schemes can be switched out, upgraded, or
removed on the fly without anyone really noticing.

So, what is this module all about then?  Well, for now, nothing but this
documentation.  If the user wants versioning, they'll have to do it themselves,
(keeping in mind that the system *will* store those local versions, and they
can rest easy knowing that they can be retrieved).  At some future point, we
will implement some fancy versioning layer with local delta compression in this
module to 'complete the package,' but it is currently a low priority endeavor.
Its priority will rise as we get close to providing a 'for your grandma'
solution.
"""
