// Orders the loader's class-2 completion before the first sector it owes, under instant CD reads.
#pragma once

#include <cstdint>

class Core;

namespace tekken3::cd {

// Guest memory and the one guest call this order needs.
class Machine {
public:
  virtual ~Machine() = default;
  virtual std::uint8_t read8(std::uint32_t address) const = 0;
  virtual std::uint32_t read32(std::uint32_t address) const = 0;
  virtual void deliverChainCompletion(std::uint32_t eventClass) = 0;
  virtual void runInterruptService() = 0;
};

// Retail delivers the class-2 completion from the VBlank timer before the drive's first sector; with
// instant reads the sector's INT1 comes first. Run before the ready hook handles a data-ready INT.
void completeReadBeforeSector(Machine &machine, std::uint32_t eventClass);

// The command writer flushes pending INT flags first. Retail serviced a sector INT1 before the next
// command; with instant reads it is still pending at the flush and would be discarded unread.
void serviceInterruptsBeforeFlush(Machine &machine);

// False for a class-2 completion that arrives after its read already finished.
[[nodiscard]] bool chainCompletionApplies(const Machine &machine, std::uint32_t eventClass);

// Wraps the ready hook (FUN_8008F850), the chain completion callback (FUN_8006C26C) and the INT flush (FUN_800842E0).
void installOverrides(Core &core);

} // namespace tekken3::cd
