// cd_protocol.h — Tekken's linked-libcd command, response and completion lifecycle.
//
// The guest's CD driver is a callback loop whose only termination signal is its own registered
// callback being invoked, so completing a CD operation without delivering that callback deletes the
// loop. Every function here is that delivery contract; the guest's own CD bytes still come from the
// framework's stock-libcd owners.
#pragma once

#include <cstdint>

class Core;

namespace tekken3::cd {

// Narrow machine boundary shared by the shipping Core adapter and the hermetic libcd contract.
// This module owns Tekken's linked-library state transitions; the adapter alone owns Lightrec guest
// calls and guest memory access.
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

// Deliver the CD completions a just-finished native operation owes, in the order retail's controller
// interrupt invoked them, and return how many were delivered.
//
// `interruptedReturnPc` is the guest return address the override interrupted. Passing the live `r31`
// is what an exception entry would restore, so the guest sees its own caller on return.
std::uint32_t deliverCompletions(Machine &machine, std::uint32_t interruptedReturnPc);

std::uint32_t synchronize(Machine &machine, std::uint32_t mode, std::uint32_t result);
std::uint32_t ready(Machine &machine, std::uint32_t mode, std::uint32_t result);
std::uint32_t queueRead(Machine &machine, std::uint32_t location, std::uint32_t sectors, std::uint32_t destination);
std::uint32_t queueResult(Machine &machine);
std::uint32_t control(
    Machine &machine, std::uint8_t command, std::uint32_t parameters, std::uint32_t result, std::uint32_t asyncMode);

// Replace Tekken's linked libcd synchronization owners with the same command/response contract,
// without their VSync-based timeout clocks. Original calls enter the guest bodies through Lightrec.
void installOverrides(Core &core);

} // namespace tekken3::cd
