# Testing Utilities

doctest is the preferred unit-testing strategy in flud, and unit tests should be written before code implementation where possible. However, much of the network code cannot be tested in this way, so custom testing utilities have been written to make correctness and load-testing easier.

flud.test contains more tests than are currently documented here. These tests are usually installed to /usr/lib/python2.4/site-packages/flud/test/

## FludPrimitiveTest.py

FludPrimitiveTest.py performs one test on each of the storage primitives: ID, STORE, VERIFY, RETRIEVE, and DELETE. The test is completely self-contained. A succesful run looks like the following:

 ```sh
 $ python FludPrimitiveTest.py
 starting testID
 starting testSTORE
 starting testRETRIEVE
 starting testVERIFY
 starting testDELETE
 all tests PASSED
 $
 ```

## FludkPrimitiveTest.py

FludkPrimitiveTest.py tests all of the DHT (metadata layer) primitives: ID, SendkFindNode/kFindNode, SendkStore/kStore, and SendkFindValue/kFindValue. It is completely self-contained. A typical invocation should look like this:

```sh
$ python FludkPrimitiveTest.py
16:28:04 test INFO: testing against localhost:8080, localport=None
16:28:04 test INFO: testkGetID PASSED
16:28:04 test INFO: attempting sendkFindNode
16:28:04 test INFO: testSendkFindNode PASSED
16:28:04 test INFO: attempting kFindNode
16:28:04 test INFO: testkFindNode PASSED
16:28:04 test INFO: attempting testSendkStore
16:28:04 test INFO: testSendkStore PASSED
16:28:04 test INFO: attempting testkStore
16:28:04 test INFO: testkStore PASSED
16:28:04 test INFO: attempting testSendkFindValue
16:28:04 test INFO: testSendkFindVal PASSED
16:28:04 test INFO: attempting testkFindValue
16:28:04 test INFO: testkFindVal PASSED
16:28:04 test INFO: all tests PASSED
```

## Emulated flud Networks

The current release of flud is geared towards testing and vetting emulated flud networks, as well as testing live flud networks among trusted nodes. Some tools to aid in the deployment of emulated flud networks are described below.

### start-fludnodes

start-fludnodes can be used to spawn multiple flud nodes on a single host.

'start-fludnodes N' will start up N nodes on increasing ports, creating FLUDHOME directories residing in ~/.fludNN where necessary.

### stop-fludnodes

stop-fludnodes is the corresponding method for stopping a batch of fludnodes started with start-fludnodes.

'stop-fludnodes N' will terminate N nodes.

### clean-fludnodes

clean-fludnodes will remove data and metadata from all ~/.fludNN directories.

### fludlocalclient

fludlocalclient connects to a specific FludNode and provides an interactive environment where you can issue commands, such as storing files, performing verify operations, etc. A typical invocation looks like this:

 ```sh
 FLUDHOME=~/.flud26 fludlocalclient
 ```

Where FLUDHOME indicates the directory containing the personality for the desired flud node. If FLUDHOME is ommitted, it defaults to ~/.flud.

fludlocalclient contains its own help. Type 'help' at the fludlocalclient prompt.



# Testing with Emulated flud Networks

## flud Network Emulation Tools

To start an emulated flud network of N nodes, do:

```sh
$ start-fludnodes N
```

To view storage consumed by flud nodes in an emulated flud network, do:

```sh
$ gauges-fludnodes ~/.flud 1-N
```

(note that you can stop and start nodes interactively with the gauges panel)

To stop the emulated flud network of N nodes, do:

```sh
$ stop-fludnodes N
```
To clean out data from all emulated flud nodes, do:

```sh
$ clean-fludnodes
```

## Testing for Massive Failure (of nodes storing my data)

The following demonstrates the persistence of backed-up data even when a large portion of the flud backup network has failed. We do this by starting a local flud group with 75 nodes, failing 1/3rd of the nodes, and operating normally with only 2/3rd of the nodes. This should always work, except in extremely unlikely circumstances [insert statistical analysis here]. In fact, you should be able to completely recover data in instances where more than 1/3rd of the nodes fail.

### Method 1: start 75 flud nodes on a single host
We can start the 75 nodes at once:

```sh
$ start-fludnodes 75
```
Which will invoke 75 flud daemons, each with their own .fludX directory in $HOME. After running this command, you should have ~/.flud1 - ~/.flud75.

Now, with 75 nodes running, you could try storing some data, etc., then kill some of the nodes and see if you can recover the data. killNnodes.sh makes this easy:

```sh
$ stop-fludnodes 20
```
Will kill the first 20 instances started with startNodes above.


If you wanted to start some additional nodes later, you could do:

```sh
$ FLUDSTART=76 start-fludnodes 25 localhost 8084
```
(the FLUDSTART env variable just tells startNnodes to use ports 76 spots higher than the default, so that we don't try to reuse unavailable ports from the first invocation. The last two options indicate where the first node should try to bootstrap, so that the two pools of nodes can talk to each other.)

The same syntax can be used with stop-fludnodes to stop nodes in any range.

### Method 2: start 50 nodes on one host, 25 on another
Start nodes as above, but split the nodes between two machines. The start-fludnodes invocation on the second machine should give one of the nodes on the first machine as the gateway, so that the two pools can see each other.

Of course, the start-fludnodes and stop-fludnodes scripts are just a convenience. You can examine them to see how they start and stop nodes if you'd rather do this manually. For now, note that the pid for each instance is stored in ~/.fludX/twistd.pid, and the twistd log is similarly stored ast twistd.log.

## Testing for Single Catastrophic Failure (of my node)
Suppose we lose our own node (the hard drive crashes, or the computer gets destroyed or stolen). This test case emulates such a failure and its recovery.

XXX: should really do the deed; send off credentials, remove the entire client .fludX dir, restore, etc.

Use start-fludnodes to bring up N nodes (where N is > 20)
Start up FludLocalClient for one of the nodes:
```sh
FLUDHOME=~/.flud5 fludlocalclient
```
Store a file[s]:
```sh
putf filename[s]
```
Store all metadata:
```sh
> putm
```
Destroy the node:
```sh
> exit
> rm ~/.flud5/dht/*
> rm ~/.flud5/meta/*
> rm ~/.flud5/store/*
```
Start up the FludLocalClient once again:
```sh
FLUDHOME=~/.flud5 fludlocalclient
```
See that master metadata is gone:
```sh
> list
```
Recover master metadata:
```sh
> getm
```
See that it worked:
```sh
> list
```
Recover the file[s]:
```sh
> getf filename[s]
```
