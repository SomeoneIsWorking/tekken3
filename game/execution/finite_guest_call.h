#pragma once

#include "execution_exit.h"

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

class Core;

namespace tekken3::execution {

// Entry registers belong to the outer call; live registers belong to the exit PC.
struct GuestCallEntry {
  std::uint32_t address = 0;
  std::uint32_t returnPc = 0;
  std::array<std::uint32_t, 5> arguments{}; // a0-a3 and t1
};

class FiniteGuestCall {
public:
  static GuestCallEntry captureEntry(const Core &core, std::uint32_t address);
  static std::string describe(Core &core, GuestCallEntry entry, const psx::cpu::ExecutionResult &result);

  // Runs one display field and aborts with describe() if the guest does not return.
  static void callToReturn(Core &core, std::uint32_t address, std::string_view owner);
};

} // namespace tekken3::execution
