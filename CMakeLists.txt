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

add_executable(tekken3_decompressor_probe_contract tests/decompressor_probe_contract.cpp)
target_link_libraries(tekken3_decompressor_probe_contract PRIVATE tekken3_runtime)
add_test(NAME tekken3_decompressor_probe_contract COMMAND tekken3_decompressor_probe_contract)
add_executable(tekken3_decompressor_lightrec tests/decompressor_lightrec.cpp)
target_link_libraries(tekken3_decompressor_lightrec PRIVATE tekken3_runtime)
add_test(
  NAME tekken3_decompressor_lightrec_selftest
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_decompressor_lightrec.py" --selftest)
add_custom_target(
  tekken3_decompressor_probe_contract_check
  COMMAND "$<TARGET_FILE:tekken3_decompressor_probe_contract>"
  DEPENDS tekken3_decompressor_probe_contract
  USES_TERMINAL
  VERBATIM)

# The SIO0 census carries its own control — eight decodings re-derived from a separate hand reading
# of the same image, which is how it caught a wrong branch offset in its own expectations. It is
# registered so that control runs in the gate, and so a decoder that starts disagreeing with the
# image is red rather than quietly answering the port question with a plausible wrong address.
add_test(
  NAME tekken3_sio_poll_census_selftest
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/tekken3_sio_poll_census.py"
          --selftest)

# Test-only. Runs the authenticated image's own pad-wait loop through the shipping Lightrec
# executor; tools/verify_pad_wait_exit.py owns the decision and its selftest.
add_executable(tekken3_pad_wait_exit tests/pad_wait_exit.cpp)
target_link_libraries(tekken3_pad_wait_exit PRIVATE tekken3_runtime)
add_test(
  NAME tekken3_pad_wait_exit_selftest
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_pad_wait_exit.py" --selftest)

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
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_stage_wedge.py"
    --selftest --exe "${TEKKEN3_EXE}"
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_focal_length.py"
    --selftest --exe "${TEKKEN3_EXE}"
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/probe_wedge_extent_census.py"
    --selftest --exe "${TEKKEN3_EXE}"
  COMMAND
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/probe_global_writers.py" --selftest "${TEKKEN3_EXE}"
  COMMAND
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/probe_dma_sync_mode.py" "${TEKKEN3_EXE}"
  COMMAND
    "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_vsync_field_clock.py"
    --selftest --exe "${TEKKEN3_EXE}"
  USES_TERMINAL
  VERBATIM)
# The 4:3-vs-16:9 receipt logic, a real `add_test` and NOT another COMMAND inside the aggregate target
# above. Two of its checks are scope checks rather than receipt checks: this title is already 60 fps, so
# an fps60 row reported as ACTIVE is a defect, and a tracked settings file containing `fps60=1` is a
# defect. The selftest half needs no disc, no GPU and no product; the pair itself is a maintainer run
# because it needs the user's CHD and the machine's single product slot. See docs/issues/0015.
add_test(
  NAME tekken3_widescreen_pair_selftest
  COMMAND
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/probe_tekken3_widescreen_pair.py" --selftest)
add_test(
  NAME tekken3_projection_selftest
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_projection.py"
    --selftest --exe "${TEKKEN3_EXE}")
add_test(
  NAME tekken3_stage_wedge_selftest
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_stage_wedge.py"
    --selftest --exe "${TEKKEN3_EXE}")
# The title-card flow: the mode and phase dispatches, the CD read mode 2 phase 8 waits on, the card
# it draws while it waits, and the single byte copy that leaves. The selftest half needs only the
# provisioned executable; the real half is the same run, since every fact is read out of the image
# rather than from a product. See docs/issues/0016.
add_test(
  NAME tekken3_title_flow_selftest
  COMMAND
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_title_flow.py" --selftest --exe "${TEKKEN3_EXE}")
add_test(
  NAME tekken3_title_flow
  COMMAND
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_title_flow.py" --exe "${TEKKEN3_EXE}")
add_test(
  NAME tekken3_focal_length_selftest
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_focal_length.py"
    --selftest --exe "${TEKKEN3_EXE}")
# Where the 20 mode handlers come from: three independent routes to the same bytes (the disc, a live
# `dumpram` capture, and mode 0's LZ payloads decoded offline) with a control that can fail. The
# selftest is the registered half; it needs only the provisioned executable, and it is what keeps the
# route-B "0 of 11" reading interpretable by proving the instrument finds what IS there first. The
# capture-fed half is a maintainer run against a real run's scratch capture, not a gate, because a
# RAM dump is not an asset-free input. See docs/issues/0018.
add_test(
  NAME tekken3_recover_runtime_handlers_selftest
  COMMAND
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/recover_runtime_handlers.py" --selftest)
add_test(
  NAME tekken3_extent_census
  COMMAND
    "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/probe_wedge_extent_census.py"
    --exe "${TEKKEN3_EXE}")
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
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/psxport_sync.py" --check
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
    tekken3_tool_selftests
    tekken3_widescreen_contract_check
    tekken3_widescreen_stage_wedge_contract_check
  USES_TERMINAL
  VERBATIM)
if(TARGET tekken3_product_help_contract_check)
  add_dependencies(verify tekken3_product_help_contract_check)
endif()

# THE LIVE PIN CHECK. Not a selftest: this runs the real function against this repository's real
# psxport.pin and the real build receipt, so it can fail when the pin is actually wrong.
#
# MEASURED 2026-09-27: every port in the workspace registered only a SELFTEST of the check function, run
# against a temporary fixture. A selftest asserts the function behaves; it cannot fail when this repo's
# pin is stale, which is why ten ports reported green while four pins were demonstrably stale. --build
# points at THIS build directory, configured moments ago, so the receipt is current by construction and
# the staleness guard cannot fire spuriously. Verified: perturbing psxport.pin turns it red.
# NOT guarded by if(BUILD_TESTING): this repository calls enable_testing() directly and never defines
# that variable, so a guarded registration here is silently INERT. That is the same failure as the
# workspace-wide one this test exists to fix -- a registration that reads as present and runs nothing --
# caught in the act on the port that was missing the gate. Verified: ctest -N went 17 -> 18.
add_test(
  NAME tekken3_psxport_pin_live
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/psxport_sync.py"
          --check --build "${CMAKE_BINARY_DIR}")

# The pin tool's own behaviour: the staleness guard, and a bump that records the commit the build
# RESOLVED rather than the framework's current HEAD. Added because 7 of 10 ports shipped the tool with no
# test gating it at all. Unguarded on purpose where this repository does not define BUILD_TESTING -- a
# guarded add_test there is silently inert, which is the failure this gate exists to prevent.
add_test(
  NAME tekken3_psxport_pin_selftest
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_psxport_sync.py")
