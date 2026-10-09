#include "cd/sector_ready_order.h"

#include "cd/loader_lifecycle.h"
#include "core.h"
#include "execution/finite_guest_call.h"
#include "execution_exit.h"
#include "native_dispatch.h"

namespace tekken3::cd {
namespace {

constexpr std::uint32_t kA0 = 4u;
constexpr std::uint32_t kRa = 31u;

class CoreMachine final : public Machine {
public:
  explicit CoreMachine(Core &core) : core_(core) {}

  std::uint8_t read8(std::uint32_t address) const override {
    return core_.mem_r8(address);
  }

  std::uint32_t read32(std::uint32_t address) const override {
    return core_.mem_r32(address);
  }

  void deliverChainCompletion(std::uint32_t eventClass) override {
    core_.r[kA0] = eventClass;
    core_.r[kRa] = loader::kReadyHookTail;
    execution::FiniteGuestCall::callToReturn(core_, loader::kChainCompletionCallback, "Tekken3 CD chain completion");
  }

  void runInterruptService() override {
    core_.r[kRa] = loader::kReadyHookTail;
    execution::FiniteGuestCall::callToReturn(core_, loader::kCdIsr, "Tekken3 CD interrupt service");
  }

private:
  Core &core_;
};

bool sectorCallbackInstalled(const Machine &machine) {
  return machine.read32(loader::kSectorCallbackFlag) == 1u;
}

void readyHookOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  CoreMachine machine(*core);
  completeReadBeforeSector(machine, caller.r[kA0] & 0xFFu);
  static_cast<R3000 &>(*core) = caller;
  psx::cpu::callOriginalToReturn(
      *core, loader::kReadyHook, psx::cpu::ExecutionBudget::currentTurn(*core), "Tekken3 CD ready hook");
}

void flushOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  CoreMachine machine(*core);
  serviceInterruptsBeforeFlush(machine);
  static_cast<R3000 &>(*core) = caller;
  psx::cpu::callOriginalToReturn(
      *core, loader::kFlushInterrupts, psx::cpu::ExecutionBudget::currentTurn(*core), "Tekken3 CD interrupt flush");
}

void chainCompletionOverride(Core *core) {
  const CoreMachine machine(*core);
  if (!chainCompletionApplies(machine, core->r[kA0] & 0xFFu)) {
    return;
  }
  psx::cpu::callOriginalToReturn(*core,
                                 loader::kChainCompletionCallback,
                                 psx::cpu::ExecutionBudget::currentTurn(*core),
                                 "Tekken3 CD chain completion");
}

} // namespace

void completeReadBeforeSector(Machine &machine, std::uint32_t eventClass) {
  if (eventClass != loader::kSectorEventClass || machine.read8(loader::kHeldByte) == 0 ||
      sectorCallbackInstalled(machine)) {
    return;
  }
  machine.deliverChainCompletion(loader::kChainCompletionClass);
}

void serviceInterruptsBeforeFlush(Machine &machine) {
  if (machine.read8(loader::kHeldByte) != 0) {
    machine.runInterruptService();
  }
}

bool chainCompletionApplies(const Machine &machine, std::uint32_t eventClass) {
  return eventClass != loader::kChainCompletionClass || machine.read8(loader::kHeldByte) != 0;
}

void installOverrides(Core &core) {
  psx::cpu::installNativeOverride(core, loader::kFlushInterrupts, "Tekken3::cdFlushInterrupts", flushOverride);
  psx::cpu::installNativeOverride(core, loader::kReadyHook, "Tekken3::cdReadyHook", readyHookOverride);
  psx::cpu::installNativeOverride(
      core, loader::kChainCompletionCallback, "Tekken3::cdChainCompletion", chainCompletionOverride);
}

} // namespace tekken3::cd
