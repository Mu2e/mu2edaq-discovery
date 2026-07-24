cmake_minimum_required(VERSION 3.16)
project(mu2edaq_discovery_cpp VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Library target. Consumers add this directory (FetchContent or add_subdirectory)
# and link `mu2edaq_discovery::mu2edaq_discovery`.
add_library(mu2edaq_discovery src/Responder.cpp)
add_library(mu2edaq_discovery::mu2edaq_discovery ALIAS mu2edaq_discovery)

target_include_directories(mu2edaq_discovery PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>)

find_package(Threads REQUIRED)
target_link_libraries(mu2edaq_discovery PUBLIC Threads::Threads)

# Only build tests/examples when this is the top-level project (not when
# pulled in via FetchContent by a consumer).
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    option(MU2EDAQ_DISCOVERY_BUILD_TESTS "Build C++ tests" ON)
    option(MU2EDAQ_DISCOVERY_BUILD_EXAMPLES "Build C++ examples" ON)
else()
    option(MU2EDAQ_DISCOVERY_BUILD_TESTS "Build C++ tests" OFF)
    option(MU2EDAQ_DISCOVERY_BUILD_EXAMPLES "Build C++ examples" OFF)
endif()

if(MU2EDAQ_DISCOVERY_BUILD_EXAMPLES)
    add_executable(responder_demo examples/responder_demo.cpp)
    target_link_libraries(responder_demo PRIVATE mu2edaq_discovery)
endif()

if(MU2EDAQ_DISCOVERY_BUILD_TESTS)
    enable_testing()
    add_executable(test_json tests/test_json.cpp)
    target_link_libraries(test_json PRIVATE mu2edaq_discovery)
    add_test(NAME json COMMAND test_json)

    # Regression coverage for issue #4.
    add_executable(test_invalid_numbers tests/test_invalid_numbers.cpp)
    target_link_libraries(test_invalid_numbers PRIVATE mu2edaq_discovery)
    add_test(NAME invalid_json_numbers COMMAND test_invalid_numbers)

    add_executable(test_responder tests/test_responder.cpp)
    target_link_libraries(test_responder PRIVATE mu2edaq_discovery)
    add_test(NAME responder COMMAND test_responder)
    set_tests_properties(responder PROPERTIES SKIP_RETURN_CODE 77)
endif()

include(GNUInstallDirs)
install(TARGETS mu2edaq_discovery
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
