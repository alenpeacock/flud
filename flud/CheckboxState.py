
"""
CheckboxState.py, (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

CheckboxState represents the states which a checkbox in DirCtrl can take
"""

class CheckboxState:
    (UNSELECTED, SELECTED, SELECTEDCHILD, SELECTEDPARENT, EXCLUDED, 
            EXCLUDEDCHILD) = range(6)
    
    def offset(oldstate, newstate):
        return newstate - oldstate
    offset = staticmethod(offset)

