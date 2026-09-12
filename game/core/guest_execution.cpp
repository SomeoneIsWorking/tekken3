#include "guest_execution.h"

#include "core.h"
#include "decompressor_probe.h"
#include "execution_exit.h"
#include "lightrec_executor.h"
#include "native_dispatch.h"

#include <cstdlib>
#include <lucent/log.h>

namespace tekken3::guest {
namespace {

psx::cpu::NativeKey keyFor(Core &core, std::uint32_t address, const char *owner) {
  const auto image = core.currentImageIdentity(address);
  if (!image) {
    lucent::error("tekken3-guest", "{} has no authenticated image identity for guest address 0x{:08X}", owner, address);
    std::abort();
  }
  return {*image, address};
}

void requireReturn(const psx::cpu::ExecutionResult &result, const char *owner) {
  if (!psx::cpu::requireGuestReturn(result, owner)) {
    std::abort();
  }
}

} // namespace

bool BoundedCall::start(
    Core &core, std::uint32_t address, std::uint32_t returnPc, const char *owner, psx::cpu::ExecutionBudget budget) {
  if (pending_) {
    lucent::error("tekken3-guest", "{} started a second call while 0x{:08X} is suspended", owner, entry_);
    std::abort();
  }
  entry_ = address;
  returnPc_ = returnPc;
  suspensions_ = 0;
  core.r[31] = returnPc;
  return accept(core, psx::cpu::dispatchGuest(core, address, budget), owner);
}

bool BoundedCall::resume(Core &core, const char *owner, psx::cpu::ExecutionBudget budget) {
  if (!pending_) {
    lucent::error("tekken3-guest", "{} resumed without a suspended guest call", owner);
    std::abort();
  }
  // dispatchGuest would take the live nested r31 as its new boundary. Keep both the guest
  // register file and the outer return PC from the original call unchanged.
  auto attribution = core.callAttribution.scope(entry_);
  return accept(core, core.lightrecExecutor().executeFunction(resumePc_, returnPc_, budget), owner);
}

bool BoundedCall::pending() const {
  return pending_;
}

bool BoundedCall::accept(Core &core, const psx::cpu::ExecutionResult &result, const char *owner) {
  if (result.returned()) {
    if (pending_) {
      lucent::info("tekken3-guest",
                   "{} returned entry 0x{:08X} to 0x{:08X} after {} suspended field(s)",
                   owner,
                   entry_,
                   returnPc_,
                   suspensions_);
    }
    pending_ = false;
    return true;
  }
  if (result.reason == psx::cpu::ExecutionExitReason::BudgetExhausted) {
    if (result.cycles == 0 || result.guestPc == 0) {
      lucent::error("tekken3-guest", "{} exhausted a turn without guest progress at 0x{:08X}", owner, result.guestPc);
      std::abort();
    }
    resumePc_ = result.guestPc;
    pending_ = true;
    ++suspensions_;
    if (suspensions_ == 1) {
      lucent::info("tekken3-guest",
                   "{} suspended entry 0x{:08X} at 0x{:08X} after {} cycles; outer_return=0x{:08X} live_ra=0x{:08X}",
                   owner,
                   entry_,
                   resumePc_,
                   result.cycles,
                   returnPc_,
                   core.r[31]);
    }
    return false;
  }
  requireReturn(result, owner);
  std::abort();
}

void call(Core &core, std::uint32_t address, const char *owner) {
  auto entry = DecompressorProbe::captureEntry(core, address);
  auto result = psx::cpu::dispatchGuest(core, address, psx::cpu::ExecutionBudget::currentTurn(core));
  if (!result.returned()) {
    lucent::error("tekken3-lz", "{}", DecompressorProbe::describe(core, entry, result));
  }
  requireReturn(result, owner);
}

void callOriginal(Core &core, std::uint32_t address, const char *owner) {
  requireReturn(
      psx::cpu::callOriginal(core, keyFor(core, address, owner), psx::cpu::ExecutionBudget::currentTurn(core)), owner);
}

void install(Core &core, std::uint32_t address, const char *name, NativeFunction function) {
  if (!function) {
    lucent::error("tekken3-guest", "{} has no native implementation", name);
    std::abort();
  }
  if (!core.nativeDispatcher().install({keyFor(core, address, name), name, function})) {
    lucent::error("tekken3-guest", "{} could not install its native override", name);
    std::abort();
  }
}

} // namespace tekken3::guest
