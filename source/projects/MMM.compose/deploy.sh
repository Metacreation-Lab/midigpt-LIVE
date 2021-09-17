#!/bin/bash

mkdir ../../../externals/MMM.compose.mxo/Contents/Frameworks

cp -f /usr/local/opt/protobuf/lib/libprotobuf.28.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libprotobuf.28.dylib
cp -f /usr/local/opt/libtorch/lib/libc10.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libc10.dylib
cp -f /usr/local/opt/libtorch/lib/libtorch.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libtorch.dylib
cp -f /usr/local/opt/libtorch/lib/libtorch_cpu.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libtorch_cpu.dylib

chmod +w ../../../externals/MMM.compose.mxo/Contents/Frameworks/libtorch_cpu.dylib

install_name_tool -change /usr/local/opt/protobuf/lib/libprotobuf.28.dylib @loader_path/../Frameworks/libprotobuf.28.dylib ../../../externals/MMM.compose.mxo/Contents/MacOS/MMM.compose
install_name_tool -change /usr/local/opt/libtorch/lib/libc10.dylib @loader_path/../Frameworks/libc10.dylib ../../../externals/MMM.compose.mxo/Contents/MacOS/MMM.compose
install_name_tool -change /usr/local/opt/libtorch/lib/libtorch.dylib @loader_path/../Frameworks/libtorch.dylib ../../../externals/MMM.compose.mxo/Contents/MacOS/MMM.compose
install_name_tool -change /usr/local/opt/libtorch/lib/libtorch_cpu.dylib @loader_path/../Frameworks/libtorch_cpu.dylib ../../../externals/MMM.compose.mxo/Contents/MacOS/MMM.compose
install_name_tool -change /usr/local/opt/protobuf/lib/libprotobuf.28.dylib @loader_path/../Frameworks/libprotobuf.28.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libtorch_cpu.dylib
install_name_tool -change /usr/local/opt/protobuf/lib/libprotobuf.28.dylib @loader_path/../Frameworks/libprotobuf.28.dylib ../../../externals/MMM.compose.mxo/Contents/Frameworks/libtorch.dylib

cp -f deployment/Info.plist ../../../externals/MMM.compose.mxo/Contents/Info.plist

mkdir ../../../externals/MMM.compose.mxo/Contents/Resources/models
cp -f deployment/models/*.pt ../../../externals/MMM.compose.mxo/Contents/Resources/models/
