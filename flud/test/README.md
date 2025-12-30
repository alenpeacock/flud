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
