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

pids=""

let seqstart=$i
let seqend=$1+$i-1

for i in `seq $seqstart $seqend`; do
	export FLUDHOME="${HOME}/.flud${i}"
	pidfile="$FLUDHOME/twistd.pid"
	pids="$pids `cat $pidfile`"
done

echo "killing $pids"
kill $pids
