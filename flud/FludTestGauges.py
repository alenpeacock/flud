#!/usr/bin/env python3
"""
FludTestGauges.py (c) 2003-2006 Alen Peacock.  This program is distributed
under the terms of the GNU General Public License (the GPL), version 3.

Provides gauges for visualizing storage for multiple flud nodes running on 
the same host.  This is really only useful for demos and testing.
"""
import sys, os, signal, stat, random, subprocess, time, shutil
import wx
import wx.lib.buttons as buttons

from flud.FludConfig import FludConfig
import flud.FludNode

dutotal = 0
def visit(arg, top, files):
    global dutotal
    for file in files:
        dutotal += os.lstat("%s" % (os.path.join(top,file)))[stat.ST_SIZE]
    arg += dutotal

def du(dir):
    total = 0
    for root, _, files in os.walk(dir):
        for name in files:
            total += os.lstat(os.path.join(root, name))[stat.ST_SIZE]
    return total

# XXX: too much manual layout.  should convert to a managed layout to allow for
# resizing, etc.
SGAUGEWIDTH = 230  # storage gauge
DGAUGEWIDTH = 100  # dht gauge
GAUGEHEIGHT = 20
ROWHEIGHT = 30
SEP = 5
LABELWIDTH = 20
POWERWIDTH = 100
RATIOBARHEIGHT = 70
COLWIDTH = SGAUGEWIDTH+DGAUGEWIDTH+LABELWIDTH+POWERWIDTH
COLGAPFUDGE = 30

class FludTestGauges(wx.Frame):

    def __init__(self, parent, title, dirroot, dirs):
        screenHeight = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_Y)-100
        rowheight = ROWHEIGHT+SEP
        height = len(dirs)*(rowheight)+RATIOBARHEIGHT
        columns = round(height / screenHeight + 1) 
        width = COLWIDTH*columns
        if columns > 1:
            height = round((len(dirs)/columns)*(rowheight)+RATIOBARHEIGHT+80)
            if (len(dirs) % columns) > 0:
                height += rowheight

        height += 35
        wx.Frame.__init__(self, parent, wx.ID_ANY, title, size=(width,height),
                style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)

        self.storebarend = 1024
        self.smultiplier = 100.0 / self.storebarend
        self.sdivisor = 1
        self.sbytelabel = ""
        self.dhtbarend = 512
        self.dmultiplier = 100.0 / self.dhtbarend
        self.ddivisor = 1
        self.dbytelabel = ""

        self.storeheading = wx.StaticText(self, -1, "block storage",
                (LABELWIDTH+POWERWIDTH, 15))
        self.totaldht = wx.StaticText(self, -1, "metadata",
                (LABELWIDTH+POWERWIDTH+SGAUGEWIDTH+SEP, 15))
        self.gauges = []
        curCol = 0
        curRow = 30
        for i in range(len(dirs)):
            self.gauges.append(wx.Gauge(self, -1, 100, 
                    (curCol*COLWIDTH+LABELWIDTH+POWERWIDTH, curRow),
                    (SGAUGEWIDTH, GAUGEHEIGHT)))
            if hasattr(self.gauges[i], "SetBezelFace"):
                self.gauges[i].SetBezelFace(3)
            if hasattr(self.gauges[i], "SetShadowWidth"):
                self.gauges[i].SetShadowWidth(3)
            self.gauges[i].SetValue(0)
            self.gauges[i].dir = "%s%s" % (dirroot,dirs[i])
            os.environ['FLUDHOME'] = self.gauges[i].dir;
            conf = FludConfig()
            conf.load(doLogging = False)
            print("%s" % conf.nodeID)
            self.gauges[i].idlabel = wx.StaticText(self, -1, "%s" % conf.nodeID,
                    (curCol*COLWIDTH+POWERWIDTH+LABELWIDTH, curRow+20))
            font = self.gauges[i].idlabel.GetFont()
            font.SetPointSize(6)
            self.gauges[i].idlabel.SetFont(font)
            self.gauges[i].dhtgauge = wx.Gauge(self, -1, 100,
                    (curCol*COLWIDTH+LABELWIDTH+POWERWIDTH+SGAUGEWIDTH+SEP, 
                        curRow), 
                    (round(SGAUGEWIDTH/3), GAUGEHEIGHT))
            self.gauges[i].power = wx.Button(self, i, "turn OFF %2s" % dirs[i],
                    (curCol*COLWIDTH+SEP, curRow),
                    (POWERWIDTH, ROWHEIGHT))
            #self.gauges[i].power = buttons.GenBitmapToggleButton(self, i, 
            #       None, 
            #       (LABELWIDTH+SGAUGEWIDTH+2*SEP+SGAUGEWIDTH/3, curRow),
            #       (POWERWIDTH, ROWHEIGHT))
            #self.gauges[i].button.SetBestSize()
            if hasattr(self.gauges[i].power, "SetToolTip"):
                self.gauges[i].power.SetToolTip("power on/off")
            else:
                self.gauges[i].power.SetToolTipString("power on/off")
            self.Bind(wx.EVT_BUTTON, self.onClick, self.gauges[i].power)

            curRow += rowheight
            if curRow > height-RATIOBARHEIGHT:
                curCol += 1
                curRow = 30

        self.totalstore = wx.StaticText(self, -1, "total: 0",
                (LABELWIDTH+POWERWIDTH, height-70))
        self.totaldht = wx.StaticText(self, -1, "total: 0",
                (LABELWIDTH+SGAUGEWIDTH+SEP+POWERWIDTH, height-70))
        self.ratiogauge = wx.Gauge(self, -1, 100,
                                   (LABELWIDTH+POWERWIDTH, height-55), 
                                   (SGAUGEWIDTH, 10))
        self.ratiogauge.SetValue(0)

        self.Bind(wx.EVT_IDLE, self.IdleHandler)

        self.timer = wx.PyTimer(self.update)
        self.timer.Start(1000)

    def onClick(self, event):
        # XXX: note that under our current startNnodes.sh scheme, the first
        # node spawned doesn't contact anyone, so if that one is powered off
        # and then powered back on, it will not be part of the node until
        # another node pings it
        # XXX: unix-specific proc management stuff follows
        idx = event.GetId()
        print(f"idx is {idx}")
        home = self.gauges[idx].dir
        pidfile = os.path.join(home, 'twistd.pid')
        if os.path.exists(pidfile):
            print("shutting down %s" % home)
            f = open(pidfile)
            pid = int(f.read())
            f.close()
            if sys.platform == "win32":
                subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False)
            else:
                print(f'killing {pid}')
                os.kill(pid, signal.SIGTERM)
            if self._is_stopped(pid):
                try:
                    os.remove(pidfile)
                except:
                    pass
            self.gauges[idx].power.SetLabel("turn ON %2s" % (int(idx)+1))
            self.gauges[idx].Hide()
            self.gauges[idx].dhtgauge.Hide()
        else:
            print("powering up %s" % home)
            env = os.environ.copy()
            env["FLUDHOME"] = home
            prev_fludhome = os.environ.get("FLUDHOME")
            os.environ["FLUDHOME"] = home
            try:
                conf = FludConfig()
                conf.load(doLogging=False)
            finally:
                if prev_fludhome is None:
                    del os.environ["FLUDHOME"]
                else:
                    os.environ["FLUDHOME"] = prev_fludhome
            env["FLUDPORT"] = str(conf.port)
            tacfile = os.path.join(flud.FludNode.getPath(), "FludNode.tac")
            project_root = os.path.dirname(os.path.dirname(__file__))
            env["PYTHONPATH"] = (
                project_root + os.pathsep + env.get("PYTHONPATH", "")
            ).rstrip(os.pathsep)
            twistd = shutil.which("twistd")
            if twistd is None:
                cmd = [sys.executable, "-m", "twisted.scripts.twistd"]
            else:
                cmd = [twistd]
            cmd.extend(
                [
                    "-oy", tacfile,
                    "--pidfile=%s" % pidfile,
                    "--logfile=%s" % os.path.join(home, "twistd.log"),
                ]
            )
            print("starting %s" % " ".join(cmd))
            startlog = os.path.join(home, "start.log")
            with open(startlog, "ab") as logf:
                process = subprocess.Popen(
                    cmd,
                    env=env,
                    cwd=project_root,
                    stdout=logf,
                    stderr=logf,
                )
            time.sleep(0.5)
            if process.poll() is None:
                try:
                    with open(pidfile, "w") as f:
                        f.write(str(process.pid))
                except:
                    pass
            if os.path.exists(pidfile):
                self.gauges[idx].power.SetLabel("turn OFF %2s" % (int(idx)+1))
                self.gauges[idx].Show()
                self.gauges[idx].dhtgauge.Show()
            else:
                print("couldn't start node %s (twistd exited %s); see %s" %
                        (int(idx)+1, process.returncode, startlog))

    def _is_stopped(self, pid):
        if sys.platform == "win32":
            result = subprocess.run(
                    ["tasklist", "/FI", "PID eq %s" % pid],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    check=False)
            return str(pid) not in result.stdout
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        return False

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
                i.power.Disable()

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
            i.SetValue(int(round(i.storebytes*self.smultiplier)))
            i.dhtgauge.SetValue(int(round(i.dhtbytes*self.dmultiplier)))
            #print "%.2f, %.2f" % ((float(i.storebytes)/float(i.dhtbytes)), 
            #       (float(i.GetValue())/float(i.dhtgauge.GetValue())))

        self.totalstore.SetLabel("total: %.1f%s" 
                % (float(storetotal)/self.sdivisor, self.sbytelabel))
        self.totaldht.SetLabel("total: %.1f%s" 
                % (float(dhttotal)/self.ddivisor, self.dbytelabel))
        if (dhttotal+storetotal == 0):
            self.ratiogauge.SetValue(0)
        else:
            self.ratiogauge.SetValue(int(round(
                    storetotal*100/(dhttotal+storetotal))))

    def updateGauges(self, update):
        for index, value in update:
            self.monitors[index].setValue(value)

    def IdleHandler(self, event):
        pass

def main():
    if len(sys.argv) < 2:
        print("usage: %s dircommon exts" % sys.argv[0])
        print("  where exts will be appended to dircommon")
        print("  e.g., '%s /home/joe/.flud 1,2,3,4,10,15,20'"\
                % sys.argv[0])
        print("  or, '%s /home/joe/.flud 1-10,15,20'"\
                % sys.argv[0])
        print("  or, '%s 1-10,15,20' (defaults dircommon to ~/.flud)"\
                % sys.argv[0])
        sys.exit()
    if len(sys.argv) == 2:
        root = os.path.join(os.environ.get("HOME", ""), ".flud")
        exts_arg = sys.argv[1]
    else:
        root = sys.argv[1]
        exts_arg = sys.argv[2]
    exts = []
    dirs = [d.strip() for d in exts_arg.split(',')]
    for i in dirs:
        if i == "_":
            exts.append('') # undocumented, means "just dircommon"
        elif i.find('-') >= 0:
            start, end = i.split('-')
            for j in range(int(start),int(end)+1):
                exts.append(j)
        else:
            exts.append(int(i))

    app = wx.App()
    t = FludTestGauges(None, 'Flud Test Gauges', root, exts)
    t.Show(1)
    app.MainLoop()

if __name__ == '__main__':
    main()
