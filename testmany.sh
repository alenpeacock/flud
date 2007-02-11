#!/bin/bash

testhost=`hostname`
testport=8080
#testscript=./FludPrimitiveTest.py
#testscript=./FludkPrimitiveTest.py
testscript="./$2"

echo "hi" | nc localhost $testport
if [ $? -ne 0 ]; then
	echo "You must start a FludNode on $testhost listening on $testport"
	exit 1;
fi

for i in `seq 1 $1`; do
	export FLUDHOME="${HOME}/.flud${i}"
	let listenport=8180+$i
	echo "starting $testscript $testhost $testport $listenport FLUDHOME=$FLUDHOME"
	python $testscript $testhost $testport $listenport &
	sleep 1;
done
