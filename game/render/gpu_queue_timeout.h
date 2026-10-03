// gpu_queue_timeout.h — Tekken's linked-libgpu queue timeout and reset contract.
//
// The retail implementation reads libetc VSync(-1) only as a timeout clock, and that call returns
// the guest's own VBlank field count (tekken3::field::kCounter) — not a host counter, which nothing in
// this product advances. So this protocol receives exactly the word the retail VSync returned, which
// is what keeps the deadline it arms comparable with the twenty other timeout arms the guest reads
// the same way.
#pragma once

#include <cstdint>

class Core;

namespace tekken3::render {

// Narrow boundary for the queue timeout owner: guest reads and writes, plus the two things this
// module is not allowed to do itself — enter a guest body, and judge the GPU.
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

// Arm the queue deadline from the guest field counter, and poll it. A non-negative poll result is a
// live queue; -1 means the deadline passed and the queue has been reset.
void armDeadline(QueueMachine &machine);
[[nodiscard]] std::int32_t pollQueue(QueueMachine &machine);

// Replace the two linked GPU timeout-clock functions that query guest VSync. Original calls enter
// the guest bodies through Lightrec; all GPU command production and queue draining remain retail.
void installOverrides(Core &core);

} // namespace tekken3::render
