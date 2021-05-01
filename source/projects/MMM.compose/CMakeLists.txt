# Copyright 2018 The Min-DevKit Authors. All rights reserved.
# Use of this source code is governed by the MIT License found in the License.md file.

cmake_minimum_required(VERSION 3.0)

project(MMM.compose)

set(C74_MIN_API_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../min-api)
include(${C74_MIN_API_DIR}/script/min-pretarget.cmake)
# set(Torch_DIR /Users/bltzr/dev/miniforge_x86_64/envs/pytorch_x86/lib/python3.8/site-packages/torch/share/cmake/Torch)


#############################################################
# MAX EXTERNAL
#############################################################

set(CMAKE_PREFIX_PATH  /usr/local/lib/)

add_subdirectory("MMM_API/")

find_package(Protobuf REQUIRED)
find_package(Torch REQUIRED)

include_directories( 
	${C74_INCLUDES}
    ${Protobuf_INCLUDE_DIRS}
    ${TORCH_INCLUDE_DIRS}c
)

set( SOURCE_FILES
	${PROJECT_NAME}.cpp
)


add_library( 
	${PROJECT_NAME} 
	MODULE
	${SOURCE_FILES}
)

target_link_libraries(
    MMM.compose
    PRIVATE
            ${Protobuf_LIBRARIES}
            ${TORCH_LIBRARIES}
            midifile
)




include(${C74_MIN_API_DIR}/script/min-posttarget.cmake)


#############################################################
# UNIT TEST
#############################################################

include(${C74_MIN_API_DIR}/test/min-object-unittest.cmake)
