# CMake generated Testfile for 
# Source directory: /Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose
# Build directory: /Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
if("${CTEST_CONFIGURATION_TYPE}" MATCHES "^([Dd][Ee][Bb][Uu][Gg])$")
  add_test(MMM.compose_test "/Users/bltzr/Documents/Max 8/Packages/MMM/tests/MMM.compose_test")
  set_tests_properties(MMM.compose_test PROPERTIES  _BACKTRACE_TRIPLES "/Users/bltzr/Documents/Max 8/Packages/MMM/source/min-api/test/min-object-unittest.cmake;71;add_test;/Users/bltzr/Documents/Max 8/Packages/MMM/source/min-api/test/min-object-unittest.cmake;0;;/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/CMakeLists.txt;39;include;/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/CMakeLists.txt;0;")
elseif("${CTEST_CONFIGURATION_TYPE}" MATCHES "^([Rr][Ee][Ll][Ee][Aa][Ss][Ee])$")
  add_test(MMM.compose_test "/Users/bltzr/Documents/Max 8/Packages/MMM/tests/MMM.compose_test")
  set_tests_properties(MMM.compose_test PROPERTIES  _BACKTRACE_TRIPLES "/Users/bltzr/Documents/Max 8/Packages/MMM/source/min-api/test/min-object-unittest.cmake;71;add_test;/Users/bltzr/Documents/Max 8/Packages/MMM/source/min-api/test/min-object-unittest.cmake;0;;/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/CMakeLists.txt;39;include;/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/CMakeLists.txt;0;")
elseif("${CTEST_CONFIGURATION_TYPE}" MATCHES "^([Mm][Ii][Nn][Ss][Ii][Zz][Ee][Rr][Ee][Ll])$")
  add_test(MMM.compose_test "/Users/bltzr/Documents/Max 8/Packages/MMM/tests/MinSizeRel/MMM.compose_test")
  set_tests_properties(MMM.compose_test PROPERTIES  _BACKTRACE_TRIPLES "/Users/bltzr/Documents/Max 8/Packages/MMM/source/min-api/test/min-object-unittest.cmake;71;add_test;/Users/bltzr/Documents/Max 8/Packages/MMM/source/min-api/test/min-object-unittest.cmake;0;;/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/CMakeLists.txt;39;include;/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/CMakeLists.txt;0;")
elseif("${CTEST_CONFIGURATION_TYPE}" MATCHES "^([Rr][Ee][Ll][Ww][Ii][Tt][Hh][Dd][Ee][Bb][Ii][Nn][Ff][Oo])$")
  add_test(MMM.compose_test "/Users/bltzr/Documents/Max 8/Packages/MMM/tests/RelWithDebInfo/MMM.compose_test")
  set_tests_properties(MMM.compose_test PROPERTIES  _BACKTRACE_TRIPLES "/Users/bltzr/Documents/Max 8/Packages/MMM/source/min-api/test/min-object-unittest.cmake;71;add_test;/Users/bltzr/Documents/Max 8/Packages/MMM/source/min-api/test/min-object-unittest.cmake;0;;/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/CMakeLists.txt;39;include;/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/CMakeLists.txt;0;")
else()
  add_test(MMM.compose_test NOT_AVAILABLE)
endif()
subdirs("mock")
