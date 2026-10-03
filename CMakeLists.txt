cmake_minimum_required(VERSION 3.24)
project(tekken3_port LANGUAGES C CXX)

enable_testing()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# PSXPORT_DIR — the framework. external/psxport is NOT a git submodule (2026-08-16): it is a relative
# symlink to the workspace's live framework checkout, or a clone of its main where there is none;
# tools/psxport_fetch.py --auto establishes whichever applies. Defaults to external/psxport so
# a bare clone of this repo builds standalone.
set(PSXPORT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/psxport" CACHE PATH
    "psxport framework source directory (default: external/psxport)")
if(NOT EXISTS "${PSXPORT_DIR}/cmake/psxport.cmake")
  message(FATAL_ERROR "PSXPORT_DIR=${PSXPORT_DIR} has no cmake/psxport.cmake — run "
                      "`python3 tools/psxport_fetch.py --auto`, or point PSXPORT_DIR at a psxport checkout.")
endif()
add_subdirectory("${PSXPORT_DIR}" psxport_build)

add_library(
  tekken3_runtime STATIC
  game/core/cd_sync.cpp
  game/core/decompressor_probe.cpp
  game/core/frame_loop.cpp
  game/core/gpu_sync.cpp
  game/core/tekken3_runtime.cpp
  game/core/sync_native.cpp
  game/core/vsync_field_clock.cpp
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

add_executable(tekken3_bounded_guest_call tests/bounded_guest_call.cpp)
target_link_libraries(tekken3_bounded_guest_call PRIVATE tekken3_runtime)
add_test(NAME tekken3_bounded_guest_call COMMAND tekken3_bounded_guest_call)
add_custom_target(
  tekken3_bounded_guest_call_check
  COMMAND "$<TARGET_FILE:tekken3_bounded_guest_call>"
  DEPENDS tekken3_bounded_guest_call
  USES_TERMINAL
  VERBATIM)

add_executable(tekken3_mode_call_budget_resume tests/mode_call_budget_resume.cpp)
target_link_libraries(tekken3_mode_call_budget_resume PRIVATE tekken3_runtime)
add_test(NAME tekken3_mode_call_budget_resume COMMAND tekken3_mode_call_budget_resume)
add_custom_target(
  tekken3_mode_call_budget_resume_check
  COMMAND "$<TARGET_FILE:tekken3_mode_call_budget_resume>"
  DEPENDS tekken3_mode_call_budget_resume
  USES_TERMINAL
  VERBATIM)

add_executable(tekken3_loader_lifecycle_contract tests/loader_lifecycle_contract.cpp)
target_link_libraries(tekken3_loader_lifecycle_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_loader_lifecycle_contract
         COMMAND tekken3_loader_lifecycle_contract "${CMAKE_CURRENT_SOURCE_DIR}/scratch/bin/tekken3/SLUS_004.02")
set_tests_properties(tekken3_loader_lifecycle_contract PROPERTIES SKIP_RETURN_CODE 77)
add_custom_target(
  tekken3_loader_lifecycle_contract_check
  COMMAND "$<TARGET_FILE:tekken3_loader_lifecycle_contract>"
          "${CMAKE_CURRENT_SOURCE_DIR}/scratch/bin/tekken3/SLUS_004.02"
  DEPENDS tekken3_loader_lifecycle_contract
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

add_executable(tekken3_vsync_field_clock_contract tests/vsync_field_clock_contract.cpp)
target_link_libraries(tekken3_vsync_field_clock_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_vsync_field_clock_contract COMMAND tekken3_vsync_field_clock_contract)
add_custom_target(
  tekken3_vsync_field_clock_contract_check
  COMMAND "$<TARGET_FILE:tekken3_vsync_field_clock_contract>"
  DEPENDS tekken3_vsync_field_clock_contract
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

add_executable(tekken3_widescreen_stage_wedge_contract tests/widescreen_stage_wedge_contract.cpp)
target_link_libraries(tekken3_widescreen_stage_wedge_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_widescreen_stage_wedge_contract COMMAND tekken3_widescreen_stage_wedge_contract)
add_custom_target(
  tekken3_widescreen_stage_wedge_contract_check
  COMMAND "$<TARGET_FILE:tekken3_widescreen_stage_wedge_contract>"
  DEPENDS tekken3_widescreen_stage_wedge_contract
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

# The real check, not a selftest of a helper: it parses game/core/vsync_field_clock.h and diffs the
# constants the product SHIPS against what it measures out of the authenticated executable. Unguarded
# on purpose, as this repository never defines BUILD_TESTING.
add_test(
  NAME tekken3_vsync_field_clock
  COMMAND
    "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_vsync_field_clock.py"
    --exe "${TEKKEN3_EXE}")
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
  COMMAND "${CMAKE_COMMAND}" -E echo
          "[verify] aggregate: product composition, policy and title contract checks"
  DEPENDS
    cpp_policy
    tekken3_cd_protocol_contract_check
    tekken3_decompressor_probe_contract_check
    tekken3_frame_loop_contract_check
    tekken3_bounded_guest_call_check
    tekken3_gpu_sync_contract_check
    tekken3_vsync_field_clock_contract_check
    tekken3_runtime_contract_check
    tekken3_runtime_seam_check
    tekken3_widescreen_contract_check
    tekken3_widescreen_stage_wedge_contract_check
  USES_TERMINAL
  VERBATIM)
if(TARGET tekken3_product_help_contract_check)
  add_dependencies(verify tekken3_product_help_contract_check)
endif()
