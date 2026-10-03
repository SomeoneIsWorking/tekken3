#pragma once

#include "execution_exit.h"

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

class Core;

namespace tekken3 {

// Diagnostic snapshot at the same guest-call boundary used by the shipping frame driver.
// Entry registers belong to the outer call; live registers belong to the exit PC.
struct GuestCallEntry {
  std::uint32_t address = 0;
  std::uint32_t returnPc = 0;
  std::array<std::uint32_t, 5> arguments{}; // a0-a3 and t1
};

class DecompressorProbe {
public:
  static GuestCallEntry captureEntry(const Core &core, std::uint32_t address);
  static std::string describe(Core &core, GuestCallEntry entry, const psx::cpu::ExecutionResult &result);

  // The single finite guest call this title makes: one display field through the product dispatcher,
  // required to return, and REFUSED with the probe's account of the call when it does not. The
  // refusal text is why this call belongs here rather than at a call site.
  static void callToReturn(Core &core, std::uint32_t address, std::string_view owner);
};

} // namespace tekken3
