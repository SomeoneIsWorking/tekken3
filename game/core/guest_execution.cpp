#include "guest_execution.h"

#include "core.h"
#include "decompressor_probe.h"
#include "execution_exit.h"
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
