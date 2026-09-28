#pragma once

#include <cstdint>

class Core;

namespace tekken3 {

// Narrow machine boundary shared by the shipping Core adapter and the hermetic libcd contract.
// CdProtocol owns Tekken's linked-library state transitions; the adapter alone owns Lightrec guest
// calls and guest memory access.
class CdMachine {
public:
  virtual ~CdMachine() = default;
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

class CdProtocol {
public:
  // Deliver the CD completions a just-finished native operation owes, in the order retail's
  // controller interrupt invoked them. Native ownership completes each CD operation inline, and
  // this title's guest CD driver is a callback loop whose only termination signal is its own
  // registered callback being invoked, so completing without delivering deletes that loop.
  //
  // `interruptedReturnPc` is the guest return address the override interrupted. Passing the live
  // `r31` is what an exception entry would restore, so the guest sees its own caller on return.
  static std::uint32_t deliverCompletions(CdMachine &machine, std::uint32_t interruptedReturnPc);

  static std::uint32_t synchronize(CdMachine &machine, std::uint32_t mode, std::uint32_t result);
  static std::uint32_t ready(CdMachine &machine, std::uint32_t mode, std::uint32_t result);
  static std::uint32_t
  queueRead(CdMachine &machine, std::uint32_t location, std::uint32_t sectors, std::uint32_t destination);
  static std::uint32_t queueResult(CdMachine &machine);
  static std::uint32_t control(CdMachine &machine,
                               std::uint8_t command,
                               std::uint32_t parameters,
                               std::uint32_t result,
                               std::uint32_t asyncMode);
};

// Replace Tekken's linked libcd synchronization owners with the same command/response contract,
// without their VSync-based timeout clocks. Original calls enter the guest bodies through Lightrec.
void installCdOverrides(Core &core);

} // namespace tekken3
