# flud backup

flud backup is experimental software. This release *is not* meant for use as a reliable backup mechanism. It is capable of performing backup and restore of data, especially among networks of trusted nodes, or for experiments and measurements on emulated flud networks contained on a single computer. The software is very much a work in progress, and major components of the architecture are not complete.

The next releases of flud backup will contain functional trust and fairness mechanisms that will allow, for the first time, the instantiation of the public flud network. Until then, this release serves as a preview and experimentation platform.

## Installation

See `INSTALL` for guidance on installing flud backup.

## Running

Start a flud node:

```sh
fludnode <bootstraphost> <bootstrapport>
```

If this is the first node in the flud network, you can omit the bootstrap host and port. When the public flud network becomes more generally available, an alternate mechanism will be used to automatically find and use it.

Other processes:

```sh
fludscheduler      # start the scheduler
fludclient         # start the graphical interface
fludlocalclient    # start a command-line client
```

All of the above commands honor the `FLUDHOME` environment variable for alternate locations of the `~/.flud` directory.

## Experimenting

Start an emulated flud network of N nodes:

```sh
start-fludnodes N
```

View storage consumed by flud nodes in an emulated flud network:

```sh
gauges-fludnodes ~/.flud 1-n
```

Stop the emulated flud network of N nodes:

```sh
stop-fludnodes N
```

Clean out data from all emulated flud nodes:

```sh
clean-fludnodes
```

See http://www.flud.org/wiki/Emulated_flud_Networks for instructions and examples of how to run and test emulated flud networks.

See http://www.flud.org/wiki/Testing_Utilities for instructions on running some of the test suites.

## Feedback

All discussion, feedback, and bug reports should be directed to the flud-devel mailing list at `flud-devel@flud.org` (archive and subscriber information at http://flud.org/mailman/listinfo/flud-devel_flud.org).
