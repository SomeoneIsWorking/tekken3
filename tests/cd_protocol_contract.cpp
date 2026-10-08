#include "cd/cd_protocol.h"

#include <cstdint>
#include <cstdio>
#include <unordered_map>
#include <vector>

namespace {

constexpr std::uint32_t kVsync = 0x800859A8u;
constexpr std::uint32_t kAckStatus = 0x80099A30u;
constexpr std::uint32_t kCompleteStatus = 0x80099A31u;
constexpr std::uint32_t kReadyCompleteStatus = 0x80099A32u;
constexpr std::uint32_t kParameterCounts = 0x80099998u;
constexpr std::uint32_t kCompleteExpected = 0x80099898u;
constexpr std::uint32_t kCurrentCommand = 0x80099771u;
constexpr std::uint32_t kSetlocParameters = 0x8009976Cu;
constexpr std::uint32_t kAckResponse = 0x800A3BE0u;
constexpr std::uint32_t kCompleteResponse = 0x800A3BE8u;
constexpr std::uint32_t kQueueBusy = 0x8009B8A8u;
constexpr std::uint32_t kQueueFlags = 0x8009B888u;
constexpr std::uint32_t kQueueThirdArgument = 0x8009B88Cu;
constexpr std::uint32_t kQueueSecondArgument = 0x8009B890u;

// Chain addresses are restated here so the test cannot share a wrong constant with the implementation.
constexpr std::uint32_t kChainCursor = 0x800A3E3Cu;
constexpr std::uint32_t kChainLive = 0x800A3E40u;
constexpr std::uint32_t kChainDepth = 8u;
constexpr std::uint32_t kGuestEventEntry = 0x8008E928u;
constexpr std::uint32_t kEventDataReady = 2u;
constexpr std::uint32_t kInterruptedReturnPc = 0x8000FFFCu;

struct Call {
  std::uint32_t address;
  std::uint32_t returnPc;
  std::uint32_t a0;
  std::uint32_t a1;
};

class RecordingCdMachine final : public tekken3::cd::Machine {
public:
  void call(std::uint32_t address, std::uint32_t returnPc) override {
    calls.push_back({address, returnPc, 0, 0});
  }

  void call2(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1) override {
    calls.push_back({address, returnPc, a0, a1});
    // Retail's class-2 branch advances the ring cursor (0x8008EA1C); the fixture models that word.
    if (address != kGuestEventEntry) {
      return;
    }
    ++guestEvents;
    if (!guestEventAdvancesTheChain) {
      return;
    }
    const std::uint32_t cursor = words.count(kChainCursor) != 0 ? words[kChainCursor] : 0;
    words[kChainCursor] = cursor + 1;
    const auto live = words.find(kChainLive);
    if (live != words.end() && live->second > 0) {
      --live->second;
    }
  }

  std::uint32_t returnValue() const override {
    return 0;
  }

  std::uint8_t read8(std::uint32_t address) const override {
    const auto found = bytes.find(address);
    return found == bytes.end() ? 0 : found->second;
  }

  std::uint32_t read32(std::uint32_t address) const override {
    const auto found = words.find(address);
    return found == words.end() ? 0 : found->second;
  }

  void write8(std::uint32_t address, std::uint8_t value) override {
    bytes[address] = value;
  }

  void write32(std::uint32_t address, std::uint32_t value) override {
    words[address] = value;
  }

  void completeSync(std::uint32_t mode, std::uint32_t result) override {
    syncMode = mode;
    syncResult = result;
    ++syncCompletions;
    zeroResult(result);
  }

  void completeCommand(std::uint8_t command, std::uint32_t parameters, std::uint32_t result) override {
    completedCommand = command;
    completedParameters = parameters;
    commandResult = result;
    ++commandCompletions;
    zeroResult(result);
  }

  bool readSectors(std::uint32_t location, std::uint32_t sectors, std::uint32_t destination) override {
    readLocation = location;
    readSectorCount = sectors;
    readDestination = destination;
    ++sectorReads;
    return sectorReadSucceeds;
  }

  bool called(std::uint32_t address) const {
    for (const Call &call : calls) {
      if (call.address == address) {
        return true;
      }
    }
    return false;
  }

  void zeroResult(std::uint32_t result) {
    if (result == 0) {
      return;
    }
    for (std::uint32_t offset = 0; offset < 8; ++offset) {
      bytes[result + offset] = 0;
    }
  }

  std::unordered_map<std::uint32_t, std::uint8_t> bytes;
  std::unordered_map<std::uint32_t, std::uint32_t> words;
  std::vector<Call> calls;
  std::uint32_t syncMode = 0;
  std::uint32_t syncResult = 0;
  std::uint32_t completedParameters = 0;
  std::uint32_t commandResult = 0;
  std::uint32_t syncCompletions = 0;
  std::uint32_t commandCompletions = 0;
  std::uint32_t readLocation = 0;
  std::uint32_t readSectorCount = 0;
  std::uint32_t readDestination = 0;
  std::uint32_t sectorReads = 0;
  std::uint8_t completedCommand = 0;
  bool sectorReadSucceeds = true;
  bool guestEventAdvancesTheChain = true;
  std::uint32_t guestEvents = 0;
};

bool syncCompletesNatively() {
  RecordingCdMachine machine;
  constexpr std::uint32_t result = 0x80001000u;
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    machine.bytes[result + offset] = 0xA5u;
  }
  if (tekken3::cd::synchronize(machine, 1, result) != 2 || machine.syncCompletions != 1 || machine.syncMode != 1 ||
      machine.syncResult != result || machine.read8(kAckStatus) != 2 || machine.called(kVsync)) {
    return false;
  }
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    if (machine.read8(result + offset) != 0) {
      return false;
    }
  }
  return true;
}

bool missingParametersAreRefused() {
  RecordingCdMachine machine;
  constexpr std::uint8_t command = 2;
  machine.write32(kParameterCounts + command * 4u, 4);
  return tekken3::cd::control(machine, command, 0, 0, 0) == static_cast<std::uint32_t>(-2) &&
         machine.syncCompletions == 0 && machine.commandCompletions == 0 && !machine.called(kVsync);
}

bool controlPreservesTitleStateAndUsesNativeController() {
  RecordingCdMachine machine;
  constexpr std::uint8_t command = 2;
  constexpr std::uint32_t parameters = 0x80002000u;
  constexpr std::uint32_t result = 0x80003000u;
  machine.write32(kParameterCounts + command * 4u, 4);
  machine.write32(kCompleteExpected + command * 4u, 1);
  for (std::uint32_t offset = 0; offset < 4; ++offset) {
    machine.bytes[parameters + offset] = static_cast<std::uint8_t>(0x10u + offset);
  }
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    machine.bytes[result + offset] = 0xA5u;
  }

  if (tekken3::cd::control(machine, command, parameters, result, 0) != 0 || machine.syncCompletions != 1 ||
      machine.commandCompletions != 1 || machine.completedCommand != command ||
      machine.completedParameters != parameters || machine.commandResult != result || machine.read8(kAckStatus) != 2 ||
      machine.read8(kCompleteStatus) != 2 || machine.read8(kCurrentCommand) != command || machine.called(kVsync)) {
    return false;
  }
  for (std::uint32_t offset = 0; offset < 4; ++offset) {
    if (machine.read8(kSetlocParameters + offset) != static_cast<std::uint8_t>(0x10u + offset)) {
      return false;
    }
  }
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    if (machine.read8(result + offset) != 0) {
      return false;
    }
  }
  return true;
}

bool asynchronousWrapperStillCompletesWithoutAWait() {
  RecordingCdMachine machine;
  constexpr std::uint8_t command = 1;
  return tekken3::cd::control(machine, command, 0, 0, 1) == 0 && machine.syncCompletions == 1 &&
         machine.commandCompletions == 1 && machine.read8(kAckStatus) == 2 && !machine.called(kVsync);
}

bool readyConsumesNativeResponsesWithoutAWait() {
  RecordingCdMachine machine;
  constexpr std::uint32_t result = 0x80004000u;
  machine.bytes[kCompleteStatus] = 3;
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    machine.bytes[kAckResponse + offset] = static_cast<std::uint8_t>(0x20u + offset);
  }
  if (tekken3::cd::ready(machine, 1, result) != 3 || machine.read8(kCompleteStatus) != 0 || machine.called(kVsync)) {
    return false;
  }
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    if (machine.read8(result + offset) != static_cast<std::uint8_t>(0x20u + offset)) {
      return false;
    }
  }

  machine.bytes[kCompleteStatus] = 3;
  machine.bytes[kReadyCompleteStatus] = 5;
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    machine.bytes[kCompleteResponse + offset] = static_cast<std::uint8_t>(0x40u + offset);
  }
  if (tekken3::cd::ready(machine, 0, result) != 5 || machine.read8(kReadyCompleteStatus) != 0 ||
      machine.read8(kCompleteStatus) != 3 || machine.called(kVsync)) {
    return false;
  }
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    if (machine.read8(result + offset) != static_cast<std::uint8_t>(0x40u + offset)) {
      return false;
    }
  }
  return true;
}

bool queueReadIsSynchronousAndPublishesItsResult() {
  RecordingCdMachine machine;
  constexpr std::uint32_t location = 0x80005000u;
  constexpr std::uint32_t sectors = 3;
  constexpr std::uint32_t destination = 0x80006000u;
  if (tekken3::cd::queueRead(machine, location, sectors, destination) != 1 || machine.sectorReads != 1 ||
      machine.readLocation != location || machine.readSectorCount != sectors ||
      machine.readDestination != destination || machine.read32(kQueueFlags) != 0x200u ||
      machine.read32(kQueueThirdArgument) != destination || machine.read32(kQueueSecondArgument) != 0 ||
      machine.read32(kQueueBusy) != 0 || tekken3::cd::queueResult(machine) != 0 || machine.called(kVsync)) {
    return false;
  }

  machine.sectorReadSucceeds = false;
  if (tekken3::cd::queueRead(machine, location, sectors, destination) != 0 || machine.sectorReads != 2 ||
      machine.read32(kQueueSecondArgument) != static_cast<std::uint32_t>(-1) ||
      tekken3::cd::queueResult(machine) != static_cast<std::uint32_t>(-1) || machine.called(kVsync)) {
    return false;
  }

  machine.write32(kQueueBusy, 1);
  return tekken3::cd::queueRead(machine, location, sectors, destination) == 0 && machine.sectorReads == 2 &&
         !machine.called(kVsync);
}

// A queued chain drains with the event class in a0 and the interrupted return address; an empty
// chain, an oversized live count and an out-of-pool cursor deliver nothing.
bool completionsAreDrainedAndRefusedWhenTheChainCannotServe() {
  // DRAIN: two live records, so exactly two deliveries and no more.
  RecordingCdMachine draining;
  draining.write32(kChainLive, 2);
  draining.write32(kChainCursor, 0);
  if (tekken3::cd::deliverCompletions(draining, kInterruptedReturnPc) != 2 || draining.guestEvents != 2 ||
      draining.calls.size() != 2) {
    return false;
  }
  for (const Call &call : draining.calls) {
    if (call.address != kGuestEventEntry || call.returnPc != kInterruptedReturnPc || call.a0 != kEventDataReady ||
        call.a1 != 0) {
      return false;
    }
  }
  if (draining.read32(kChainCursor) != 2 || draining.read32(kChainLive) != 0) {
    return false;
  }

  // EMPTY: nothing queued, nothing called.
  RecordingCdMachine empty;
  empty.write32(kChainLive, 0);
  if (tekken3::cd::deliverCompletions(empty, kInterruptedReturnPc) != 0 || empty.guestEvents != 0) {
    return false;
  }

  // A live count above the pool depth (guest bound at 0x8008EEA8) delivers nothing.
  RecordingCdMachine overfull;
  overfull.write32(kChainLive, kChainDepth + 1u);
  overfull.write32(kChainCursor, 0);
  if (tekken3::cd::deliverCompletions(overfull, kInterruptedReturnPc) != 0 || overfull.guestEvents != 0) {
    return false;
  }

  // A cursor outside the pool delivers nothing.
  RecordingCdMachine outside;
  outside.write32(kChainLive, 1);
  outside.write32(kChainCursor, kChainDepth);
  if (tekken3::cd::deliverCompletions(outside, kInterruptedReturnPc) != 0 || outside.guestEvents != 0) {
    return false;
  }

  // A delivery that does not move the cursor stops the drain after one entry.
  RecordingCdMachine wedged;
  wedged.guestEventAdvancesTheChain = false;
  wedged.write32(kChainLive, kChainDepth);
  wedged.write32(kChainCursor, 0);
  if (tekken3::cd::deliverCompletions(wedged, kInterruptedReturnPc) != 0 || wedged.guestEvents != 1) {
    return false;
  }
  return true;
}

} // namespace

int main() {
  if (!syncCompletesNatively() || !missingParametersAreRefused() ||
      !controlPreservesTitleStateAndUsesNativeController() || !asynchronousWrapperStillCompletesWithoutAWait() ||
      !readyConsumesNativeResponsesWithoutAWait() || !queueReadIsSynchronousAndPublishesItsResult() ||
      !completionsAreDrainedAndRefusedWhenTheChainCannotServe()) {
    std::fprintf(stderr,
                 "cd_protocol_contract: FAIL — native libcd owners diverged from the measured "
                 "wrapper, the synchronous hardware contract, or the CD completion chain\n");
    return 1;
  }
  std::printf("cd_protocol_contract: PASS — CdSync, CdReady, CdControl, and queued data reads complete "
              "through the native stock-libcd owner with title state preserved and no guest VSync, and "
              "the CD completion chain is drained within the guest's own bounds\n");
  return 0;
}
