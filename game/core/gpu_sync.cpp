#include "gpu_sync.h"

#include "core.h"
#include "game.h"
#include "guest_execution.h"

#include <cstdlib>
#include <lucent/log.h>

namespace tekken3 {
namespace {

constexpr std::uint32_t kGpuTimeoutArm = 0x8007E8F0u;
constexpr std::uint32_t kGpuTimeoutPoll = 0x8007E924u;
constexpr std::uint32_t kCriticalSection = 0x80085D44u;

constexpr std::uint32_t kGpuDataPointer = 0x80098C90u;
constexpr std::uint32_t kDmaControlPointer = 0x80098C94u;
constexpr std::uint32_t kGpuControlPointer = 0x80098C9Cu;
constexpr std::uint32_t kDmaChannelPointer = 0x80098CACu;
constexpr std::uint32_t kQueueHead = 0x80098CB0u;
constexpr std::uint32_t kQueueTail = 0x80098CB4u;
constexpr std::uint32_t kSavedCriticalSection = 0x80098CC0u;
constexpr std::uint32_t kFieldDeadline = 0x80098CC4u;
constexpr std::uint32_t kPollCount = 0x80098CC8u;

constexpr std::uint32_t kFieldTimeout = 240u;
constexpr std::uint32_t kPollTimeout = 0xF0000u;
constexpr std::uint32_t kV0 = 2u;
constexpr std::uint32_t kA0 = 4u;
constexpr std::uint32_t kRa = 31u;

class CoreGpuSyncMachine final : public GpuSyncMachine {
public:
  explicit CoreGpuSyncMachine(Core &core) : core_(core) {}

  std::uint32_t fieldCounter() const override {
    if (!core_.game) {
      lucent::error("gpu-sync", "Tekken 3 GPU timeout owner has no Game");
      std::abort();
    }
    return core_.game->timing.vblank;
  }

  std::uint32_t read32(std::uint32_t address) const override {
    return core_.mem_r32(address);
  }

  void write32(std::uint32_t address, std::uint32_t value) override {
    core_.mem_w32(address, value);
  }

  std::uint32_t setCriticalSection(std::uint32_t enabled, std::uint32_t returnPc) override {
    core_.r[kA0] = enabled;
    core_.r[kRa] = returnPc;
    guest::call(core_, kCriticalSection, "Tekken3 GPU critical-section guest call");
    return core_.r[kV0];
  }

  void reportTimeout(std::uint32_t queueDepth,
                     std::uint32_t gpuData,
                     std::uint32_t gpuControl,
                     std::uint32_t dmaControl) override {
    lucent::error("gpu-sync",
                  "Tekken 3 GPU queue timeout: depth={} GP0=0x{:08X} GP1=0x{:08X} DMA=0x{:08X}",
                  queueDepth,
                  gpuData,
                  gpuControl,
                  dmaControl);
  }

private:
  Core &core_;
};

bool signedLess(std::uint32_t lhs, std::uint32_t rhs) {
  return static_cast<std::int32_t>(lhs) < static_cast<std::int32_t>(rhs);
}

std::uint32_t dereference(GpuSyncMachine &machine, std::uint32_t pointerAddress) {
  return machine.read32(machine.read32(pointerAddress));
}

void resetGpuQueue(GpuSyncMachine &machine) {
  const std::uint32_t priorCritical = machine.setCriticalSection(0, 0x8007E9D0u);
  machine.write32(kQueueTail, 0);
  machine.write32(kSavedCriticalSection, priorCritical);
  machine.write32(kQueueHead, 0);

  machine.write32(machine.read32(kGpuControlPointer), 0x401u);
  const std::uint32_t dmaChannel = machine.read32(kDmaChannelPointer);
  machine.write32(dmaChannel, machine.read32(dmaChannel) | 0x800u);
  machine.write32(machine.read32(kGpuDataPointer), 0x02000000u);
  machine.write32(machine.read32(kGpuDataPointer), 0x01000000u);
  machine.setCriticalSection(priorCritical, 0x8007EA4Cu);
}

void gpuTimeoutArmOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  CoreGpuSyncMachine machine(*core);
  GpuSyncProtocol::arm(machine);
  static_cast<R3000 &>(*core) = caller;
}

void gpuTimeoutPollOverride(Core *core) {
  const R3000 caller = static_cast<const R3000 &>(*core);
  CoreGpuSyncMachine machine(*core);
  const std::int32_t result = GpuSyncProtocol::poll(machine);
  static_cast<R3000 &>(*core) = caller;
  core->r[kV0] = static_cast<std::uint32_t>(result);
}

} // namespace

void GpuSyncProtocol::arm(GpuSyncMachine &machine) {
  machine.write32(kFieldDeadline, machine.fieldCounter() + kFieldTimeout);
  machine.write32(kPollCount, 0);
}

std::int32_t GpuSyncProtocol::poll(GpuSyncMachine &machine) {
  bool expired = signedLess(machine.read32(kFieldDeadline), machine.fieldCounter());
  if (!expired) {
    const std::uint32_t pollCount = machine.read32(kPollCount);
    machine.write32(kPollCount, pollCount + 1u);
    expired = signedLess(kPollTimeout, pollCount);
  }
  if (!expired) {
    return 0;
  }

  machine.reportTimeout((machine.read32(kQueueHead) - machine.read32(kQueueTail)) & 63u,
                        dereference(machine, kGpuDataPointer),
                        dereference(machine, kGpuControlPointer),
                        dereference(machine, kDmaControlPointer));
  resetGpuQueue(machine);
  return -1;
}

void installGpuSyncOverrides(Core &core) {
  guest::install(core, kGpuTimeoutArm, "Tekken3::gpuTimeoutArm", gpuTimeoutArmOverride);
  guest::install(core, kGpuTimeoutPoll, "Tekken3::gpuTimeoutPoll", gpuTimeoutPollOverride);
}

} // namespace tekken3
