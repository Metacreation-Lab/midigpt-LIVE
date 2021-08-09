#!/bin/sh

cp /usr/local/lib/libprotobuf.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libprotobuf.dylib
cp /usr/local/lib/libc10.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libc10.dylib
cp /usr/local/lib/libkineto.a ../../../externals/MMM.compose.mxo/Contents/Frameworks/libkineto.a
cp MMM_API/Debug/libmidifile.a ../../../externals/MMM.compose.mxo/Contents/Frameworks/libmidifile.a
cp /usr/local/lib/libtorch.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libtorch.dylib
cp /usr/local/lib/libtorch_cpu.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libtorch_cpu.dylib

git submodule update --init --recursive
git submodule sync --recursive
cd source/projects/MMM.compose

cmake -G Xcode .

cd MMM.compose.xcodeproj
sed -i -e 's/10.11/10.14/' project.pbxproj

cd ../MMM_API/src/mmm_api/protobuf
protoc --cpp_out . midi.proto

open ../../../../MMM.compose.xcodeproj


