cmake_minimum_required(VERSION 3.24)
project(tekken3_port LANGUAGES C CXX)

enable_testing()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# PSXPORT_DIR — the framework. external/psxport is NOT a git submodule (2026-08-16): it is a symlink
# to the workspace's shared framework clone, or a private clone at this repo's psxport.pin on a fresh
# machine; tools/psxport_sync.py --auto establishes whichever applies. Defaults to external/psxport so
# a bare clone of this repo builds standalone.
set(PSXPORT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/psxport" CACHE PATH
    "psxport framework source directory (default: external/psxport)")
if(NOT EXISTS "${PSXPORT_DIR}/cmake/psxport.cmake")
  message(FATAL_ERROR "PSXPORT_DIR=${PSXPORT_DIR} has no cmake/psxport.cmake — run "
                      "`python3 tools/psxport_sync.py --auto`, or point PSXPORT_DIR at a psxport checkout.")
endif()
# RECORD WHAT THIS CONFIGURE RESOLVED, so `tools/psxport_sync.py --check` can compare the built
# framework against the one psxport.pin RECORDS.
execute_process(COMMAND git -C "${PSXPORT_DIR}" rev-parse HEAD
                OUTPUT_VARIABLE PSXPORT_RESOLVED_SHA OUTPUT_STRIP_TRAILING_WHITESPACE
                ERROR_QUIET RESULT_VARIABLE _psxport_rev_rc)
if(NOT _psxport_rev_rc EQUAL 0)
  set(PSXPORT_RESOLVED_SHA "unknown")
endif()
file(WRITE "${CMAKE_BINARY_DIR}/psxport_resolved.txt"
     "dir = ${PSXPORT_DIR}\ncommit = ${PSXPORT_RESOLVED_SHA}\n")
add_subdirectory("${PSXPORT_DIR}" psxport_build)

add_library(
  tekken3_runtime STATIC
  game/core/cd_sync.cpp
  game/core/decompressor_probe.cpp
  game/core/frame_loop.cpp
  game/core/guest_execution.cpp
  game/core/gpu_sync.cpp
  game/core/tekken3_runtime.cpp
  game/core/sync_native.cpp
  game/core/widescreen.cpp)
target_include_directories(tekken3_runtime PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/game/core")
target_compile_features(tekken3_runtime PUBLIC cxx_std_20)
target_link_libraries(tekken3_runtime PUBLIC psxport)

include(cmake/tekken3_port.cmake)

set(TEKKEN3_EXE "${CMAKE_CURRENT_SOURCE_DIR}/scratch/bin/tekken3/SLUS_004.02")

add_executable(tekken3_runtime_seam tests/runtime_seam.cpp)
target_link_libraries(tekken3_runtime_seam PRIVATE tekken3_runtime)
add_test(NAME tekken3_runtime_seam COMMAND tekken3_runtime_seam)
add_custom_target(
  tekken3_runtime_seam_check
  COMMAND "$<TARGET_FILE:tekken3_runtime_seam>"
  DEPENDS tekken3_runtime_seam
  USES_TERMINAL
  VERBATIM)

add_executable(tekken3_runtime_contract tests/runtime_contract.cpp)
target_link_libraries(tekken3_runtime_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_runtime_contract COMMAND tekken3_runtime_contract)
add_custom_target(
  tekken3_runtime_contract_check
  COMMAND "$<TARGET_FILE:tekken3_runtime_contract>"
  DEPENDS tekken3_runtime_contract
  USES_TERMINAL
  VERBATIM)

add_executable(tekken3_frame_loop_contract tests/frame_loop_contract.cpp)
target_link_libraries(tekken3_frame_loop_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_frame_loop_contract COMMAND tekken3_frame_loop_contract)
add_custom_target(
  tekken3_frame_loop_contract_check
  COMMAND "$<TARGET_FILE:tekken3_frame_loop_contract>"
  DEPENDS tekken3_frame_loop_contract
  USES_TERMINAL
  VERBATIM)

add_executable(tekken3_decompressor_probe_contract tests/decompressor_probe_contract.cpp)
target_link_libraries(tekken3_decompressor_probe_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_decompressor_probe_contract COMMAND tekken3_decompressor_probe_contract)
add_custom_target(
  tekken3_decompressor_probe_contract_check
  COMMAND "$<TARGET_FILE:tekken3_decompressor_probe_contract>"
  DEPENDS tekken3_decompressor_probe_contract
  USES_TERMINAL
  VERBATIM)

add_executable(tekken3_cd_protocol_contract tests/cd_protocol_contract.cpp)
target_link_libraries(tekken3_cd_protocol_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_cd_protocol_contract COMMAND tekken3_cd_protocol_contract)
add_custom_target(
  tekken3_cd_protocol_contract_check
  COMMAND "$<TARGET_FILE:tekken3_cd_protocol_contract>"
  DEPENDS tekken3_cd_protocol_contract
  USES_TERMINAL
  VERBATIM)

add_executable(tekken3_gpu_sync_contract tests/gpu_sync_contract.cpp)
target_link_libraries(tekken3_gpu_sync_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_gpu_sync_contract COMMAND tekken3_gpu_sync_contract)
add_custom_target(
  tekken3_gpu_sync_contract_check
  COMMAND "$<TARGET_FILE:tekken3_gpu_sync_contract>"
  DEPENDS tekken3_gpu_sync_contract
  USES_TERMINAL
  VERBATIM)

add_executable(tekken3_widescreen_contract tests/widescreen_contract.cpp)
target_link_libraries(tekken3_widescreen_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_widescreen_contract COMMAND tekken3_widescreen_contract)
add_custom_target(
  tekken3_widescreen_contract_check
  COMMAND "$<TARGET_FILE:tekken3_widescreen_contract>"
  DEPENDS tekken3_widescreen_contract
  USES_TERMINAL
  VERBATIM)

# Device-side oracle for T3-04's first hardware sequence. This compiles the vendored Mednafen IRQ
# controller itself in a separate process; it neither shares state nor an implementation with
# psxport's Core::io_read/io_write path.
add_executable(
  tekken3_irq_oracle
  tests/irq_oracle.cpp
  "${PSXPORT_DIR}/vendor/beetle-psx/mednafen/psx/irq.c")
target_include_directories(
  tekken3_irq_oracle PRIVATE
  "${PSXPORT_DIR}/vendor/beetle-psx"
  "${PSXPORT_DIR}/vendor/beetle-psx/mednafen"
  "${PSXPORT_DIR}/vendor/beetle-psx/mednafen/psx"
  "${PSXPORT_DIR}/vendor/beetle-psx/include"
  "${PSXPORT_DIR}/vendor/beetle-psx/libretro-common/include")
target_compile_features(tekken3_irq_oracle PRIVATE cxx_std_20)
add_test(NAME tekken3_irq_oracle_selftest COMMAND tekken3_irq_oracle --selftest)

add_custom_target(
  tekken3_tool_selftests
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/provision_executable.py" --selftest
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_startup.py" --selftest
  COMMAND
    "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/test_run.py"
  COMMAND
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/test_launcher_help.py"
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_projection.py"
    --selftest --exe "${TEKKEN3_EXE}"
  USES_TERMINAL
  VERBATIM)
add_test(
  NAME tekken3_projection_selftest
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_projection.py"
    --selftest --exe "${TEKKEN3_EXE}")
add_test(
  NAME tekken3_launcher_selftest
  COMMAND
    "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/test_run.py")
add_test(
  NAME tekken3_launcher_help_contract
  COMMAND
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/test_launcher_help.py")
add_custom_target(
  cpp_policy
  COMMAND
    "${Python3_EXECUTABLE}" "${PSXPORT_DIR}/tools/check_cpp_style.py"
    --root "${CMAKE_CURRENT_SOURCE_DIR}"
    --compile-commands "${CMAKE_BINARY_DIR}"
    --allow-empty-scaffold
  USES_TERMINAL
  VERBATIM)
add_custom_target(
  verify
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/psxport_sync.py" --check
  DEPENDS
    cpp_policy
    tekken3_cd_protocol_contract_check
    tekken3_decompressor_probe_contract_check
    tekken3_frame_loop_contract_check
    tekken3_gpu_sync_contract_check
    tekken3_runtime_contract_check
    tekken3_runtime_seam_check
    tekken3_tool_selftests
    tekken3_widescreen_contract_check
  USES_TERMINAL
  VERBATIM)
if(TARGET tekken3_product_help_contract_check)
  add_dependencies(verify tekken3_product_help_contract_check)
endif()
