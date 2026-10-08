// Tekken's linked-libgpu queue timeout and reset contract; the clock is the guest field counter.
#pragma once

#include <cstdint>

class Core;

namespace tekken3::render {

// Boundary for guest access, guest calls and the GPU timeout report.
class QueueMachine {
public:
  virtual ~QueueMachine() = default;
  virtual std::uint32_t fieldCounter() const = 0;
  virtual std::uint32_t read32(std::uint32_t address) const = 0;
  virtual void write32(std::uint32_t address, std::uint32_t value) = 0;
  virtual std::uint32_t setCriticalSection(std::uint32_t enabled, std::uint32_t returnPc) = 0;
  virtual void reportTimeout(std::uint32_t queueDepth,
                             std::uint32_t gpuData,
                             std::uint32_t gpuControl,
                             std::uint32_t dmaControl) = 0;
};

// pollQueue returns -1 once the deadline passed and the queue was reset.
void armDeadline(QueueMachine &machine);
[[nodiscard]] std::int32_t pollQueue(QueueMachine &machine);

// Replaces the two linked GPU timeout-clock functions that query VSync.
void installOverrides(Core &core);

} // namespace tekken3::render
