#include "cd/cd_protocol.h"

#include "cd_control.h"
#include "core.h"
#include "disc.h"
#include "execution/finite_guest_call.h"
#include "execution_exit.h"
#include "game.h"
#include "native_dispatch.h"

#include <cstdint>
#include <cstdlib>
#include <lucent/log.h>

namespace tekken3::cd {
namespace {

constexpr std::uint32_t kCdSync = 0x80083904u;
constexpr std::uint32_t kCdReady = 0x80083B84u;
constexpr std::uint32_t kCdControl = 0x80083E4Cu;
constexpr std::uint32_t kCdCommand = 0x80090D88u;
constexpr std::uint32_t kCdQueueStart = 0x80090F78u;
constexpr std::uint32_t kCdQueueResult = 0x80091328u;
constexpr std::uint32_t kDebugPrint = 0x8007A458u;

constexpr std::uint32_t kQueueBusy = 0x8009B8A8u;
constexpr std::uint32_t kQueueFlags = 0x8009B888u;
constexpr std::uint32_t kQueueThirdArgument = 0x8009B88Cu;
constexpr std::uint32_t kQueueSecondArgument = 0x8009B890u;
constexpr std::uint32_t kDefaultQueueCommand = 0x80090CA0u;

constexpr std::uint32_t kDebugLevel = 0x8009975Cu;
constexpr std::uint32_t kSetlocParameters = 0x8009976Cu;
constexpr std::uint32_t kFilterFile = 0x80099770u;
constexpr std::uint32_t kCurrentCommand = 0x80099771u;
constexpr std::uint32_t kCommandNames = 0x80099778u;
constexpr std::uint32_t kCompleteExpected = 0x80099898u;
constexpr std::uint32_t kParameterCounts = 0x80099998u;
constexpr std::uint32_t kAckStatus = 0x80099A30u;
constexpr std::uint32_t kCompleteStatus = 0x80099A31u;
constexpr std::uint32_t kReadyCompleteStatus = 0x80099A32u;
constexpr std::uint32_t kAckResponse = 0x800A3BE0u;
constexpr std::uint32_t kCompleteResponse = 0x800A3BE8u;

constexpr std::uint32_t kCommandTraceFormat = 0x80028568u;
constexpr std::uint32_t kMissingParameterFormat = 0x80028570u;

// FUN_8008E928 is the guest's CD-event entry; its class-2 branch (jalr at 0x8008EA80) is the only
// site that invokes a queued command's registered callback.
constexpr std::uint32_t kGuestEventEntry = 0x8008E928u;
constexpr std::uint32_t kEventDataReady = 2u;

// Callback record pool at 0x800A3D78: eight records (0x8008EC74), stride 24.
constexpr std::uint32_t kChainDepth = 8u;
// Ring cursor, read at 0x8008E954 and written at 0x8008EA1C.
constexpr std::uint32_t kChainCursor = 0x800A3E3Cu;
// Live-record count, bounded against the depth at 0x8008EEA8.
constexpr std::uint32_t kChainLive = 0x800A3E40u;

constexpr std::uint32_t kA0 = 4;
constexpr std::uint32_t kA1 = 5;
constexpr std::uint32_t kA2 = 6;
constexpr std::uint32_t kA3 = 7;
constexpr std::uint32_t kV0 = 2;
constexpr std::uint8_t kReady = 2;
constexpr std::uint8_t kSetloc = 2;
constexpr std::uint8_t kSetfilter = 14;
constexpr std::uint8_t kGetTn = 0x13;
constexpr std::uint8_t kGetTd = 0x14;

std::uint8_t toBcd(std::uint32_t value) {
  return static_cast<std::uint8_t>(((value / 10u) << 4u) | (value % 10u));
}

std::uint8_t fromBcd(std::uint8_t value) {
  return static_cast<std::uint8_t>((value >> 4u) * 10u + (value & 0xFu));
}

bool completeTocCommand(Core &core, std::uint8_t command, std::uint32_t parameters, std::uint32_t result) {
  if ((command != kGetTn && command != kGetTd) || result == 0) {
    return false;
  }
  DiscState &disc = core.game->disc;
  if (disc.track_count == 0 && !disc_open(&disc)) {
    lucent::error("cd-sync", "Tekken 3 TOC command 0x{:02X} could not open the configured disc", command);
    std::abort();
  }
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    core.mem_w8(result + offset, 0);
  }
  core.mem_w8(result, kReady);
  if (command == kGetTn) {
    core.mem_w8(result + 1u, toBcd(disc.tracks[0].number));
    core.mem_w8(result + 2u, toBcd(disc.tracks[disc.track_count - 1u].number));
    return true;
  }

  const std::uint8_t requested = parameters == 0 ? 0 : fromBcd(core.mem_r8(parameters));
  std::uint32_t position = 0;
  if (requested == 0) {
    const DiscTrackInfo &last = disc.tracks[disc.track_count - 1u];
    position = static_cast<std::uint32_t>(last.lba) + last.sectors + 150u;
  } else {
    for (std::uint8_t index = 0; index < disc.track_count; ++index) {
      if (disc.tracks[index].number == requested) {
        position = static_cast<std::uint32_t>(disc.tracks[index].lba) + 150u;
        break;
      }
    }
  }
  core.mem_w8(result + 1u, toBcd(position / (60u * 75u)));
  core.mem_w8(result + 2u, toBcd((position / 75u) % 60u));
  return true;
}

class CoreMachine final : public Machine {
public:
  explicit CoreMachine(Core &core) : core_(core) {}

  void call(std::uint32_t address, std::uint32_t returnPc) override {
    core_.r[31] = returnPc;
    execution::FiniteGuestCall::callToReturn(core_, address, "Tekken3 CD guest call");
  }

  void call2(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1) override {
    core_.r[kA0] = a0;
    core_.r[kA1] = a1;
    call(address, returnPc);
  }

  std::uint32_t returnValue() const override {
    return core_.r[kV0];
  }

  std::uint8_t read8(std::uint32_t address) const override {
    return core_.mem_r8(address);
  }

  std::uint32_t read32(std::uint32_t address) const override {
    return core_.mem_r32(address);
  }

  void write8(std::uint32_t address, std::uint8_t value) override {
    core_.mem_w8(address, value);
  }

  void write32(std::uint32_t address, std::uint32_t value) override {
    core_.mem_w32(address, value);
  }

  void completeSync(std::uint32_t mode, std::uint32_t result) override {
    core_.r[kA0] = mode;
    core_.r[kA1] = result;
    cd_sync_stock_sync(&core_);
  }

  void completeCommand(std::uint8_t command, std::uint32_t parameters, std::uint32_t result) override {
    if (completeTocCommand(core_, command, parameters, result)) {
      return;
    }
    core_.r[kA0] = command;
    core_.r[kA1] = parameters;
    core_.r[kA2] = result;
    cd_control_sync(&core_);
  }

  bool readSectors(std::uint32_t location, std::uint32_t sectors, std::uint32_t destination) override {
    const R3000 saved = static_cast<const R3000 &>(core_);
    core_.r[kA0] = kSetloc;
    core_.r[kA1] = location;
    core_.r[kA2] = 0;
    cd_control_sync(&core_);
    core_.r[kA0] = sectors;
    core_.r[kA1] = destination;
    core_.r[kA2] = 0;
    cd_read_stock_sync(&core_);
    const bool succeeded = core_.r[kV0] != 0;
    static_cast<R3000 &>(core_) = saved;
    return succeeded;
  }

private:
  Core &core_;
};

void traceCommand(Machine &machine, std::uint8_t command) {
  if (static_cast<std::int32_t>(machine.read32(kDebugLevel)) < 2) {
    return;
  }
  machine.call2(kDebugPrint,
                0x80083EB0u,
                kCommandTraceFormat,
                machine.read32(kCommandNames + static_cast<std::uint32_t>(command) * 4u));
}

void reportMissingParameter(Machine &machine, std::uint8_t command) {
  if (static_cast<std::int32_t>(machine.read32(kDebugLevel)) <= 0) {
    return;
  }
  machine.call2(kDebugPrint,
                0x80083F04u,
                kMissingParameterFormat,
                machine.read32(kCommandNames + static_cast<std::uint32_t>(command) * 4u));
}
void copyResponse(Machine &machine, std::uint32_t source, std::uint32_t result) {
  if (result == 0) {
    return;
  }
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    machine.write8(result + offset, machine.read8(source + offset));
  }
}

} // namespace

std::uint32_t synchronize(Machine &machine, std::uint32_t mode, std::uint32_t result) {
  machine.completeSync(mode, result);
  machine.write8(kAckStatus, kReady);
  return kReady;
}

std::uint32_t ready(Machine &machine, std::uint32_t mode, std::uint32_t result) {
  // FUN_80083B84 checks the completion slot before the acknowledgement slot; the native controller
  // has already finished, so consume the status and response buffers directly and ignore mode.
  static_cast<void>(mode);
  const std::uint8_t completion = machine.read8(kReadyCompleteStatus);
  if (completion != 0) {
    machine.write8(kReadyCompleteStatus, 0);
    copyResponse(machine, kCompleteResponse, result);
    return completion;
  }
  const std::uint8_t acknowledgement = machine.read8(kCompleteStatus);
  if (acknowledgement != 0) {
    machine.write8(kCompleteStatus, 0);
    copyResponse(machine, kAckResponse, result);
    return acknowledgement;
  }
  return 0;
}

std::uint32_t queueRead(Machine &machine, std::uint32_t location, std::uint32_t sectors, std::uint32_t destination) {
  if (machine.read32(kQueueBusy) == 1 || location == 0 || sectors == 0 || destination == 0) {
    return 0;
  }
  machine.write32(kQueueFlags, 0x200u);
  machine.write32(kQueueThirdArgument, destination);
  machine.write32(kQueueSecondArgument, sectors);
  machine.write32(kQueueBusy, 1);

  // The native read is synchronous, so the retail Pause/Setmode/Setloc/ReadN plus callback spin
  // collapses to one 0/-1 result.
  const bool succeeded = machine.readSectors(location, sectors, destination);
  machine.write32(kQueueSecondArgument, succeeded ? 0u : static_cast<std::uint32_t>(-1));
  machine.write32(kQueueBusy, 0);
  return succeeded ? 1u : 0u;
}

std::uint32_t queueResult(Machine &machine) {
  return machine.read32(kQueueSecondArgument);
}

std::uint32_t control(
    Machine &machine, std::uint8_t command, std::uint32_t parameters, std::uint32_t result, std::uint32_t asyncMode) {
  traceCommand(machine, command);
  const std::uint32_t tableOffset = static_cast<std::uint32_t>(command) * 4u;
  const std::uint32_t parameterCount = machine.read32(kParameterCounts + tableOffset);
  if (parameterCount != 0 && parameters == 0) {
    reportMissingParameter(machine, command);
    return static_cast<std::uint32_t>(-2);
  }

  synchronize(machine, 0, 0);
  if (command == kSetloc) {
    for (std::uint32_t offset = 0; offset < 4; ++offset) {
      machine.write8(kSetlocParameters + offset, machine.read8(parameters + offset));
    }
  } else if (command == kSetfilter) {
    machine.write8(kFilterFile, machine.read8(parameters));
  }

  machine.write8(kAckStatus, 0);
  const bool completeExpected = machine.read32(kCompleteExpected + tableOffset) != 0;
  if (completeExpected) {
    machine.write8(kCompleteStatus, 0);
  }
  machine.write8(kCurrentCommand, command);
  machine.completeCommand(command, parameters, result);
  machine.write8(kAckStatus, kReady);
  if (completeExpected) {
    machine.write8(kCompleteStatus, kReady);
  }

  // The linked wrapper returns 0 on both its blocking and async success paths.
  static_cast<void>(asyncMode);
  return 0;
}

namespace {

void cdSyncOverride(Core *core) {
  CoreMachine machine(*core);
  core->r[kV0] = synchronize(machine, core->r[kA0], core->r[kA1]);
}

void cdReadyOverride(Core *core) {
  CoreMachine machine(*core);
  core->r[kV0] = ready(machine, core->r[kA0], core->r[kA1]);
}

void cdControlOverride(Core *core) {
  // Captured before r31 is clobbered; the completion callbacks return here.
  const std::uint32_t interruptedReturnPc = core->r[31];
  CoreMachine machine(*core);
  core->r[kV0] = control(machine, static_cast<std::uint8_t>(core->r[kA0]), core->r[kA1], core->r[kA2], core->r[kA3]);
  deliverCompletions(machine, interruptedReturnPc);
}

void cdCommandOverride(Core *core) {
  const std::uint32_t interruptedReturnPc = core->r[31];
  const R3000 caller = static_cast<const R3000 &>(*core);
  CoreMachine machine(*core);
  const std::uint32_t result =
      control(machine, static_cast<std::uint8_t>(caller.r[kA0]), caller.r[kA1], caller.r[kA2], 0);
  static_cast<R3000 &>(*core) = caller;
  core->r[kV0] = result == 0 ? 1u : 0u;
  deliverCompletions(machine, interruptedReturnPc);
}

void dispatch(Core &core, std::uint32_t address, std::uint32_t returnPc) {
  core.r[31] = returnPc;
  execution::FiniteGuestCall::callToReturn(core, address, "Tekken3 queued CD guest call");
}

void cdQueueStartOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  const std::uint32_t interruptedReturnPc = caller.r[31];

  std::uint32_t location = caller.r[kA0];
  if (caller.r[kA0] == 0) {
    core->r[kA0] = 0;
    dispatch(*core, kDefaultQueueCommand, 0x80090FE8u);
    location = core->r[kV0];
  }
  CoreMachine machine(*core);
  const std::uint32_t queued = queueRead(machine, location, caller.r[kA1], caller.r[kA2]);
  static_cast<R3000 &>(*core) = caller;
  core->r[kV0] = queued;
  CoreMachine completed(*core);
  deliverCompletions(completed, interruptedReturnPc);
}

void cdQueueResultOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  CoreMachine machine(*core);
  const std::uint32_t value = queueResult(machine);
  static_cast<R3000 &>(*core) = caller;
  core->r[kV0] = value;
}

} // namespace

std::uint32_t deliverCompletions(Machine &machine, std::uint32_t interruptedReturnPc) {
  // Bounded by the guest's pool depth and live count; stops once a delivery leaves the cursor
  // unchanged (0x8008E974 returns early on a record whose state word is 0).
  std::uint32_t delivered = 0;
  for (std::uint32_t step = 0; step < kChainDepth; ++step) {
    const std::uint32_t live = machine.read32(kChainLive);
    if (live == 0 || live > kChainDepth) {
      break;
    }
    const std::uint32_t cursorBefore = machine.read32(kChainCursor);
    if (cursorBefore >= kChainDepth) {
      break;
    }
    // a1 = 0: the guest calls its own 0x8008FCC0 with a null status buffer at 0x8008FEE4.
    machine.call2(kGuestEventEntry, interruptedReturnPc, kEventDataReady, 0);
    if (machine.read32(kChainCursor) == cursorBefore) {
      break;
    }
    ++delivered;
  }
  return delivered;
}

void installOverrides(Core &core) {
  psx::cpu::installNativeOverride(core, kCdSync, "Tekken3::cdSync", cdSyncOverride);
  psx::cpu::installNativeOverride(core, kCdReady, "Tekken3::cdReady", cdReadyOverride);
  psx::cpu::installNativeOverride(core, kCdControl, "Tekken3::cdControl", cdControlOverride);
  psx::cpu::installNativeOverride(core, kCdCommand, "Tekken3::cdCommand", cdCommandOverride);
  psx::cpu::installNativeOverride(core, kCdQueueStart, "Tekken3::cdQueueStart", cdQueueStartOverride);
  psx::cpu::installNativeOverride(core, kCdQueueResult, "Tekken3::cdQueueResult", cdQueueResultOverride);
}

} // namespace tekken3::cd
