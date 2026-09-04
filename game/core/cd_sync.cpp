#include "cd_sync.h"

#include "cd_control.h"
#include "core.h"
#include "disc.h"
#include "game.h"
#include "guest_execution.h"

#include <cstdint>
#include <cstdlib>
#include <lucent/log.h>

namespace tekken3 {
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

class CoreCdMachine final : public CdMachine {
public:
  explicit CoreCdMachine(Core &core) : core_(core) {}

  void call(std::uint32_t address, std::uint32_t returnPc) override {
    core_.r[31] = returnPc;
    guest::call(core_, address, "Tekken3 CD guest call");
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

void traceCommand(CdMachine &machine, std::uint8_t command) {
  if (static_cast<std::int32_t>(machine.read32(kDebugLevel)) < 2) {
    return;
  }
  machine.call2(kDebugPrint,
                0x80083EB0u,
                kCommandTraceFormat,
                machine.read32(kCommandNames + static_cast<std::uint32_t>(command) * 4u));
}

void reportMissingParameter(CdMachine &machine, std::uint8_t command) {
  if (static_cast<std::int32_t>(machine.read32(kDebugLevel)) <= 0) {
    return;
  }
  machine.call2(kDebugPrint,
                0x80083F04u,
                kMissingParameterFormat,
                machine.read32(kCommandNames + static_cast<std::uint32_t>(command) * 4u));
}

std::uint32_t synchronize(CdMachine &machine, std::uint32_t mode, std::uint32_t result) {
  machine.completeSync(mode, result);
  machine.write8(kAckStatus, kReady);
  return kReady;
}

void copyResponse(CdMachine &machine, std::uint32_t source, std::uint32_t result) {
  if (result == 0) {
    return;
  }
  for (std::uint32_t offset = 0; offset < 8; ++offset) {
    machine.write8(result + offset, machine.read8(source + offset));
  }
}

std::uint32_t ready(CdMachine &machine, std::uint32_t mode, std::uint32_t result) {
  // FUN_80083B84 checks the completion-class slot before the acknowledgement-class slot. Retail's
  // VSync calls only bound an asynchronous drain loop. The native controller has already completed
  // that operation before this poll runs, so consume the title-owned status and response buffers
  // directly. Both measured callers pass non-blocking mode 1; mode 0 has the same result because no
  // second hardware owner is allowed to make progress inside this routine.
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

std::uint32_t queueRead(CdMachine &machine, std::uint32_t location, std::uint32_t sectors, std::uint32_t destination) {
  if (machine.read32(kQueueBusy) == 1 || location == 0 || sectors == 0 || destination == 0) {
    return 0;
  }
  machine.write32(kQueueFlags, 0x200u);
  machine.write32(kQueueThirdArgument, destination);
  machine.write32(kQueueSecondArgument, sectors);
  machine.write32(kQueueBusy, 1);

  // FUN_80091E5C is the sole queue-start caller and supplies a CdlLOC, sector count, and destination.
  // Retail turns that request into Pause/Setmode/Setloc/ReadN commands, then spins on callbacks that
  // decrement the remaining-sector word. Native ownership must be synchronous all the way down: use
  // the shared stock-libcd read owner for the real disc bytes, then publish the same zero/-1 result.
  const bool succeeded = machine.readSectors(location, sectors, destination);
  machine.write32(kQueueSecondArgument, succeeded ? 0u : static_cast<std::uint32_t>(-1));
  machine.write32(kQueueBusy, 0);
  return succeeded ? 1u : 0u;
}

std::uint32_t queueResult(CdMachine &machine) {
  return machine.read32(kQueueSecondArgument);
}

std::uint32_t control(
    CdMachine &machine, std::uint8_t command, std::uint32_t parameters, std::uint32_t result, std::uint32_t asyncMode) {
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

  // Native CD ownership completes the controller operation before returning. Preserve the linked
  // wrapper's return contract: both its blocking and nominally asynchronous success paths return 0.
  static_cast<void>(asyncMode);
  return 0;
}

void cdSyncOverride(Core *core) {
  CoreCdMachine machine(*core);
  core->r[kV0] = CdProtocol::synchronize(machine, core->r[kA0], core->r[kA1]);
}

void cdReadyOverride(Core *core) {
  CoreCdMachine machine(*core);
  core->r[kV0] = CdProtocol::ready(machine, core->r[kA0], core->r[kA1]);
}

void cdControlOverride(Core *core) {
  CoreCdMachine machine(*core);
  core->r[kV0] =
      CdProtocol::control(machine, static_cast<std::uint8_t>(core->r[kA0]), core->r[kA1], core->r[kA2], core->r[kA3]);
}

void cdCommandOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  CoreCdMachine machine(*core);
  const std::uint32_t result =
      CdProtocol::control(machine, static_cast<std::uint8_t>(caller.r[kA0]), caller.r[kA1], caller.r[kA2], 0);
  static_cast<R3000 &>(*core) = caller;
  core->r[kV0] = result == 0 ? 1u : 0u;
}

void dispatch(Core &core, std::uint32_t address, std::uint32_t returnPc) {
  core.r[31] = returnPc;
  guest::call(core, address, "Tekken3 queued CD guest call");
}

void cdQueueStartOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  auto finish = [&](std::uint32_t value) {
    static_cast<R3000 &>(*core) = caller;
    core->r[kV0] = value;
  };

  std::uint32_t location = caller.r[kA0];
  if (caller.r[kA0] == 0) {
    core->r[kA0] = 0;
    dispatch(*core, kDefaultQueueCommand, 0x80090FE8u);
    location = core->r[kV0];
  }
  CoreCdMachine machine(*core);
  finish(CdProtocol::queueRead(machine, location, caller.r[kA1], caller.r[kA2]));
}

void cdQueueResultOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  CoreCdMachine machine(*core);
  const std::uint32_t value = CdProtocol::queueResult(machine);
  static_cast<R3000 &>(*core) = caller;
  core->r[kV0] = value;
}

} // namespace

std::uint32_t CdProtocol::synchronize(CdMachine &machine, std::uint32_t mode, std::uint32_t result) {
  return tekken3::synchronize(machine, mode, result);
}

std::uint32_t CdProtocol::ready(CdMachine &machine, std::uint32_t mode, std::uint32_t result) {
  return tekken3::ready(machine, mode, result);
}

std::uint32_t
CdProtocol::queueRead(CdMachine &machine, std::uint32_t location, std::uint32_t sectors, std::uint32_t destination) {
  return tekken3::queueRead(machine, location, sectors, destination);
}

std::uint32_t CdProtocol::queueResult(CdMachine &machine) {
  return tekken3::queueResult(machine);
}

std::uint32_t CdProtocol::control(
    CdMachine &machine, std::uint8_t command, std::uint32_t parameters, std::uint32_t result, std::uint32_t asyncMode) {
  return tekken3::control(machine, command, parameters, result, asyncMode);
}

void installCdOverrides(Core &core) {
  guest::install(core, kCdSync, "Tekken3::cdSync", cdSyncOverride);
  guest::install(core, kCdReady, "Tekken3::cdReady", cdReadyOverride);
  guest::install(core, kCdControl, "Tekken3::cdControl", cdControlOverride);
  guest::install(core, kCdCommand, "Tekken3::cdCommand", cdCommandOverride);
  guest::install(core, kCdQueueStart, "Tekken3::cdQueueStart", cdQueueStartOverride);
  guest::install(core, kCdQueueResult, "Tekken3::cdQueueResult", cdQueueResultOverride);
}

} // namespace tekken3
