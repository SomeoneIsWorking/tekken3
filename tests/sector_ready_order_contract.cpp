#include "cd/loader_lifecycle.h"
#include "cd/sector_ready_order.h"

#include <cstdint>
#include <cstdio>
#include <unordered_map>

namespace {

class RecordingMachine final : public tekken3::cd::Machine {
public:
  std::uint8_t read8(std::uint32_t address) const override {
    return static_cast<std::uint8_t>(read32(address));
  }

  std::uint32_t read32(std::uint32_t address) const override {
    const auto found = memory.find(address);
    return found == memory.end() ? 0 : found->second;
  }

  void deliverChainCompletion(std::uint32_t eventClass) override {
    ++deliveries;
    lastClass = eventClass;
  }

  void runInterruptService() override {
    ++interruptServices;
  }

  std::unordered_map<std::uint32_t, std::uint32_t> memory;
  unsigned interruptServices = 0;
  unsigned deliveries = 0;
  std::uint32_t lastClass = 0;
};

bool failed(const char *what) {
  std::fprintf(stderr, "sector_ready_order_contract: FAIL - %s\n", what);
  return true;
}

// The first sector's INT1 reaches the ready hook before the timer-delivered completion has installed
// the sector callback: the completion is delivered first, once.
bool completionPrecedesTheFirstSector() {
  RecordingMachine machine;
  machine.memory[tekken3::loader::kHeldByte] = 1;
  tekken3::cd::completeReadBeforeSector(machine, tekken3::loader::kSectorEventClass);
  return machine.deliveries == 1 && machine.lastClass == tekken3::loader::kChainCompletionClass;
}

bool nothingIsOwedOnceInstalledOrIdle() {
  RecordingMachine installed;
  installed.memory[tekken3::loader::kHeldByte] = 1;
  installed.memory[tekken3::loader::kSectorCallbackFlag] = 1;
  tekken3::cd::completeReadBeforeSector(installed, tekken3::loader::kSectorEventClass);

  RecordingMachine idle;
  tekken3::cd::completeReadBeforeSector(idle, tekken3::loader::kSectorEventClass);

  RecordingMachine otherEvent;
  otherEvent.memory[tekken3::loader::kHeldByte] = 1;
  tekken3::cd::completeReadBeforeSector(otherEvent, 4);
  return installed.deliveries == 0 && idle.deliveries == 0 && otherEvent.deliveries == 0;
}

// A class-2 completion that arrives after the read finished must not re-install the sector callback.
bool lateCompletionIsDropped() {
  RecordingMachine finished;
  RecordingMachine waiting;
  waiting.memory[tekken3::loader::kHeldByte] = 1;
  return !tekken3::cd::chainCompletionApplies(finished, tekken3::loader::kChainCompletionClass) &&
         tekken3::cd::chainCompletionApplies(waiting, tekken3::loader::kChainCompletionClass) &&
         tekken3::cd::chainCompletionApplies(finished, 5);
}

// A read is in flight: the INT1 pending at the command writer's flush is serviced, not discarded.
bool pendingSectorIsServicedBeforeTheFlush() {
  RecordingMachine reading;
  reading.memory[tekken3::loader::kHeldByte] = 1;
  tekken3::cd::serviceInterruptsBeforeFlush(reading);
  RecordingMachine idle;
  tekken3::cd::serviceInterruptsBeforeFlush(idle);
  return reading.interruptServices == 1 && idle.interruptServices == 0;
}

} // namespace

int main() {
  if (!completionPrecedesTheFirstSector()) {
    return failed("the class-2 completion did not precede the first sector") ? 1 : 0;
  }
  if (!nothingIsOwedOnceInstalledOrIdle()) {
    return failed("a completion was delivered with nothing owed") ? 1 : 0;
  }
  if (!pendingSectorIsServicedBeforeTheFlush()) {
    return failed("a pending sector INT was not serviced before the flush") ? 1 : 0;
  }
  if (!lateCompletionIsDropped()) {
    return failed("a late class-2 completion was not dropped") ? 1 : 0;
  }
  std::printf("sector_ready_order_contract: PASS - completion ordered before the first sector, idle cases silent, late "
              "completion dropped\n");
  return 0;
}
