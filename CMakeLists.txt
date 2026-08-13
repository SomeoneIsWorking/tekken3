cmake_minimum_required(VERSION 3.24)
project(tekken3_port LANGUAGES C CXX)

set(PSXPORT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/psxport" CACHE PATH
    "Writable psxport checkout for framework development")
set(PSXPORT_BUILD_SMOKE ON CACHE BOOL "Build the framework agnosticism smoke" FORCE)
add_subdirectory("${PSXPORT_DIR}" psxport_build)
add_custom_target(tekken3_scaffold DEPENDS psxport_smoke)
