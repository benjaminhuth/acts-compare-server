#!/bin/bash

export WDIR=$PWD

function build_and_run {
    git clone --recurse-submodules "$1" src

    cd src
    git checkout -b "$2"
    cd ..

    mkdir build

    echo "Configure $1:$2"
    cmake -S src -B build \
        -G "Ninja"
        -D ACTS_BUILD_EXAMPLES=ON \
        -D ACTS_BUILD_ODD=ON \
        -D ACTS_BUILD_EXAMPLES_PYTHONBINDINGS=ON \

    echo "Build $1:$2"
    cmake --build build -- -j3

    source build/python/setup.sh
    export PYTHONPATH=src/Examples/Scripts/Python:$PYTHONPATH

    echo "Run $1:$2"
    python $WDIR/script.py > log.txt

    rm -rf build src
}


mkdir output_a
cd output_a
build_and_run $REPO_A $COMMIT_A
cd ..

mkdir output_b
cd output_b
build_and_run $REPO_B $COMMIT_B
cd ..


