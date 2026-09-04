#pragma once

#include <cstdint>

class Core;

namespace tekken3 {

// Narrow boundary for Tekken's linked GPU queue timeout owner. The retail implementation reads
// libetc VSync(-1) only as a timeout clock; the host frame loop is the sole cadence owner, so this
// protocol receives that owner's field counter directly while preserving the queue reset contract.
class GpuSyncMachine {
public:
  virtual ~GpuSyncMachine() = default;
  virtual std::uint32_t fieldCounter() const = 0;
  virtual std::uint32_t read32(std::uint32_t address) const = 0;
  virtual void write32(std::uint32_t address, std::uint32_t value) = 0;
  virtual std::uint32_t setCriticalSection(std::uint32_t enabled, std::uint32_t returnPc) = 0;
  virtual void reportTimeout(std::uint32_t queueDepth,
                             std::uint32_t gpuData,
                             std::uint32_t gpuControl,
                             std::uint32_t dmaControl) = 0;
};

class GpuSyncProtocol {
public:
  static void arm(GpuSyncMachine &machine);
  [[nodiscard]] static std::int32_t poll(GpuSyncMachine &machine);
};

// Replace the two linked GPU timeout-clock functions that query guest VSync. Original calls enter
// the guest bodies through Lightrec; all GPU command production and queue draining remain retail.
void installGpuSyncOverrides(Core &core);

} // namespace tekken3
