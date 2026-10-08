// Tekken's linked-libcd command, response and completion lifecycle.
#pragma once

#include <cstdint>

class Core;

namespace tekken3::cd {

// Machine boundary shared by the Core adapter and the libcd contract test.
class Machine {
public:
  virtual ~Machine() = default;
  virtual void call(std::uint32_t address, std::uint32_t returnPc) = 0;
  virtual void call2(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1) = 0;
  virtual std::uint32_t returnValue() const = 0;
  virtual std::uint8_t read8(std::uint32_t address) const = 0;
  virtual std::uint32_t read32(std::uint32_t address) const = 0;
  virtual void write8(std::uint32_t address, std::uint8_t value) = 0;
  virtual void write32(std::uint32_t address, std::uint32_t value) = 0;
  virtual void completeSync(std::uint32_t mode, std::uint32_t result) = 0;
  virtual void completeCommand(std::uint8_t command, std::uint32_t parameters, std::uint32_t result) = 0;
  virtual bool readSectors(std::uint32_t location, std::uint32_t sectors, std::uint32_t destination) = 0;
};

// Delivers the callbacks a finished operation owes, in retail interrupt order; returns the count.
// `interruptedReturnPc` is the live r31, so the guest sees its own caller on return.
std::uint32_t deliverCompletions(Machine &machine, std::uint32_t interruptedReturnPc);

std::uint32_t synchronize(Machine &machine, std::uint32_t mode, std::uint32_t result);
std::uint32_t ready(Machine &machine, std::uint32_t mode, std::uint32_t result);
std::uint32_t queueRead(Machine &machine, std::uint32_t location, std::uint32_t sectors, std::uint32_t destination);
std::uint32_t queueResult(Machine &machine);
std::uint32_t control(
    Machine &machine, std::uint8_t command, std::uint32_t parameters, std::uint32_t result, std::uint32_t asyncMode);

// Replaces the linked libcd sync owners with the same contract, minus their VSync timeout clocks.
void installOverrides(Core &core);

} // namespace tekken3::cd
