#!/bin/bash

testhost=`hostname`
invoker="twistd -oy FludNode.tac"

if [ -z ${FLUDSTART} ]; then
	i=1
else
	i=${FLUDSTART}
fi

if [ -z $1 ]; then
	1=0
fi

if [ -n $3 ]; then
	boothost=$2
	bootport=$3
fi

export FLUDHOME="${HOME}/.flud${i}"
let listenport=8080+$i
pidfile="$FLUDHOME/twistd.pid"
logfile="$FLUDHOME/twistd.log"
if [ -n "$boothost" ]; then
	echo "starting {$FLUDHOME} $invoker on $listenport to $boothost:$bootport"
	FLUDGWHOST=$boothost FLUDGWPORT=$bootport FLUDPORT=$listenport $invoker --pidfile=$pidfile --logfile=$logfile
else
	echo "starting {$FLUDHOME} $invoker on $listenport"
	FLUDPORT=$listenport $invoker --pidfile=$pidfile --logfile=$logfile
fi
pids[$i]=$!

let seqstart=$i+1
let seqend=$1+$i-1

for i in `seq $seqstart $seqend`; do
	export FLUDHOME="${HOME}/.flud${i}"
	testport=$listenport
	let listenport=8080+$i
	pidfile="$FLUDHOME/twistd.pid"
	logfile="$FLUDHOME/twistd.log"
	echo "starting {$FLUDHOME} $invoker on $listenport to $testhost:$testport"
	FLUDGWHOST=$testhost FLUDGWPORT=$testport FLUDPORT=$listenport $invoker --pidfile=$pidfile --logfile=$logfile
	pids[$i]=$!
done
