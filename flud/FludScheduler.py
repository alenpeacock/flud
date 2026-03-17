#!/usr/bin/env python3

import asyncio
import os
import stat
import time

from flud.CheckboxState import CheckboxState

CHECKTIME = 5


class FludScheduler:
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.fileconfigfile = None
        self.fileconfigfileMTime = 0
        self.fileChangeTime = 0
        self.fileconfigSelected = set()
        self.fileconfigExcluded = set()
        self.mastermetadata = {}

    async def getMasterMetadata(self):
        self.mastermetadata = await self.client.sendLIST()

    def readFileConfig(self, mtime=None):
        with open(self.fileconfigfile, "r") as file:
            self.fileconfig = eval(file.read())
        if mtime:
            self.fileconfigfileMTime = mtime
        else:
            self.fileconfigfileMTime = os.stat(self.fileconfigfile)[stat.ST_MTIME]
        self.fileconfigSelected = {
            f for f in self.fileconfig
            if self.fileconfig[f] in (
                CheckboxState.SELECTED, CheckboxState.SELECTEDCHILD
            )
        }
        self.fileconfigExcluded = {
            f for f in self.fileconfig
            if self.fileconfig[f] in (
                CheckboxState.EXCLUDED, CheckboxState.EXCLUDEDCHILD
            )
        }

    def fileChangedStat(self, file, fileChangeTime=None):
        if os.path.isfile(file) or os.path.isdir(file):
            mtime = os.stat(file)[stat.ST_MTIME]
            if not fileChangeTime:
                fileChangeTime = self.fileChangeTime
            if file in self.mastermetadata:
                fileChangeTime = self.mastermetadata[file][1]
            else:
                return True
            if mtime > fileChangeTime:
                return True
        return False

    def checkFileConfig(self):
        if not self.fileconfigfile:
            if "FLUDHOME" in os.environ:
                fludhome = os.environ["FLUDHOME"]
            elif "HOME" in os.environ:
                fludhome = os.environ["HOME"] + "/.flud"
            else:
                fludhome = ".flud"
            self.fileconfigfile = os.path.join(fludhome, "fludfile.conf")
            if os.path.isfile(self.fileconfigfile):
                self.readFileConfig()
                return True
        elif os.path.isfile(self.fileconfigfile):
            if self.fileChangedStat(self.fileconfigfile, self.fileconfigfileMTime):
                self.readFileConfig(time.time())
                return True
        return False

    def checkFilesystem(self):
        checkedFiles = set()
        changedFiles = set()

        def checkList(entries):
            for entry in entries:
                if (
                    entry not in checkedFiles
                    and entry not in self.fileconfigExcluded
                    and entry not in self.mastermetadata
                ):
                    if os.path.isdir(entry):
                        dirfiles = [os.path.join(entry, i) for i in os.listdir(entry)]
                        checkedFiles.update([entry])
                        checkList(dirfiles)
                    elif self.fileChangedStat(entry):
                        if os.path.isfile(entry):
                            changedFiles.update([entry])
                    checkedFiles.update([entry])

        checkList(self.fileconfigSelected)
        self.fileChangeTime = time.time()
        return changedFiles

    async def storeFiles(self, changedFiles):
        tasks = [self.client.sendPUTF(f) for f in changedFiles]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def run_forever(self):
        await self.getMasterMetadata()
        while True:
            self.checkFileConfig()
            changedFiles = self.checkFilesystem()
            if changedFiles:
                await self.storeFiles(changedFiles)
                await self.getMasterMetadata()
            await asyncio.sleep(CHECKTIME)
