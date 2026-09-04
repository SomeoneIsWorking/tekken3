# Whole-program Tekken 3 product. The authenticated executable remains runtime data; psxport's
# Lightrec executor owns every non-native guest instruction.
add_executable(
  tekken3_port
  game/core/main.cpp
  game/core/tekken3_port.cpp)
add_dependencies(tekken3_port gen_gpu_shaders)
target_compile_features(tekken3_port PRIVATE cxx_std_20)
target_include_directories(tekken3_port PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/game/core")
target_link_libraries(tekken3_port PRIVATE tekken3_runtime)
set_target_properties(
  tekken3_port PROPERTIES
  ENABLE_EXPORTS ON
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
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
