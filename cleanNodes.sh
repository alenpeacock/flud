#!/bin/bash

for i in ~/.flud*/dht/*; do rm $i; done
for i in ~/.flud*/store/*; do rm $i; done
for i in ~/.flud*/meta/*; do rm $i; done
for i in ~/.flud*/dl/*; do rm -r $i; done
