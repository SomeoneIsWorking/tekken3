// finite_guest_call.h — the one finite guest call this title makes, and how it accounts for itself.
#pragma once

#include "execution_exit.h"

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

class Core;

namespace tekken3::execution {

// Snapshot at the same guest-call boundary the shipping frame driver uses. Entry registers belong to
// the outer call; live registers belong to the exit PC.
struct GuestCallEntry {
  std::uint32_t address = 0;
  std::uint32_t returnPc = 0;
  std::array<std::uint32_t, 5> arguments{}; // a0-a3 and t1
};

class FiniteGuestCall {
public:
  static GuestCallEntry captureEntry(const Core &core, std::uint32_t address);
  static std::string describe(Core &core, GuestCallEntry entry, const psx::cpu::ExecutionResult &result);

  // One display field through the product dispatcher, required to return, and REFUSED with the
  // account of the call when it does not. The refusal text is why this call belongs here rather than
  // at a call site: the account names where the guest stopped and how far the LZ decompressor it was
  // running had got, which is what makes a stalled frame diagnosable from the log alone.
  static void callToReturn(Core &core, std::uint32_t address, std::string_view owner);
};

} // namespace tekken3::execution
