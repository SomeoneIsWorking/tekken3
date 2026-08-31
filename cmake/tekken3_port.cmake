# Whole-program Tekken 3 product. The generated substrate is gitignored and must be emitted from the
# user's identity-checked executable before configuration; absent generated input means the product
# target is honestly absent rather than replaced by a smoke or diagnostic executable.
set(TEKKEN3_PORT_GENERATED "${CMAKE_CURRENT_SOURCE_DIR}/generated/port")
if(NOT EXISTS "${TEKKEN3_PORT_GENERATED}/rec_sources.cmake")
  message(STATUS
    "tekken3_port: NOT configured — generated/port/rec_sources.cmake is absent. "
    "Provision SLUS_004.02 and run tools/ensure_recomp.py.")
  return()
endif()

include("${TEKKEN3_PORT_GENERATED}/rec_sources.cmake")
list(TRANSFORM GEN_REC_SRCS PREPEND "${TEKKEN3_PORT_GENERATED}/")
set(TEKKEN3_GENERATED_OPTIMIZATION "-O1" CACHE STRING
    "Optimization level for generated Tekken 3 bodies (-O0 is useful for short frontier builds)")
if(NOT TEKKEN3_GENERATED_OPTIMIZATION MATCHES "^-O[0123sz]$")
  message(FATAL_ERROR
    "TEKKEN3_GENERATED_OPTIMIZATION=${TEKKEN3_GENERATED_OPTIMIZATION} is not a supported optimization flag")
endif()
set_source_files_properties(
  ${GEN_REC_SRCS}
  PROPERTIES
    LANGUAGE CXX
    # Generated bodies can be several megabytes each. Cross-function inlining expands them
    # pathologically while adding no guest semantics; sibling-call optimization remains enabled so
    # emitted guest tail jumps stay bounded native tail calls. Keep debug records on first-party
    # ownership code, but not on generated bodies: the emitted function symbols retain guest-address
    # backtraces, while full line tables make the 120k-line shards take minutes each to compile.
    COMPILE_OPTIONS
      "${TEKKEN3_GENERATED_OPTIMIZATION};-fno-inline-functions;-foptimize-sibling-calls;-fno-strict-aliasing;-fwrapv;-w;-g0")

add_executable(
  tekken3_port
  game/core/main.cpp
  game/core/recomp_register.cpp
  game/core/tekken3_port.cpp
  ${GEN_REC_SRCS})
add_dependencies(tekken3_port gen_gpu_shaders)
target_compile_features(tekken3_port PRIVATE cxx_std_20)
target_include_directories(
  tekken3_port PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/game/core"
  "${TEKKEN3_PORT_GENERATED}")
target_link_libraries(tekken3_port PRIVATE tekken3_runtime)
set_target_properties(
  tekken3_port PROPERTIES
  ENABLE_EXPORTS ON
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/scratch/bin")
add_test(
  NAME tekken3_product_help_contract
  COMMAND
    "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/test_product_help.py"
    "$<TARGET_FILE:tekken3_port>")
add_custom_target(
  tekken3_product_help_contract_check
  COMMAND
    "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/test_product_help.py"
    "$<TARGET_FILE:tekken3_port>"
  DEPENDS tekken3_port
  USES_TERMINAL
  VERBATIM)
