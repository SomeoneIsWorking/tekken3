// Title-owned field turn: boot prefix, frame barrier, display init, per-field step and the driver.
#pragma once

#include "game_runtime.h"
#include "resumable_guest_call.h"

#include <cstdint>

class Game;

namespace tekken3::frame {

// Machine boundary shared by the Core adapter and the sequence tests.
class Machine {
public:
  virtual ~Machine() = default;

  virtual void call(std::uint32_t address, std::uint32_t returnPc) = 0;
  virtual void call1(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0) = 0;
  virtual void
  call3(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1, std::uint32_t a2) = 0;
  virtual bool startModeCall(std::uint32_t address, std::uint32_t returnPc) = 0;
  virtual bool resumeModeCall() = 0;
  virtual void deliverEvent(std::uint32_t eventClass, std::uint32_t spec) = 0;
  virtual std::uint32_t returnValue() const = 0;
  virtual std::uint32_t readRegister(std::uint32_t index) const = 0;
  virtual void writeRegister(std::uint32_t index, std::uint32_t value) = 0;
  virtual void tick(std::uint32_t guestInstructions) = 0;

  virtual std::uint8_t read8(std::uint32_t address) const = 0;
  virtual std::uint16_t read16(std::uint32_t address) const = 0;
  virtual std::uint32_t read32(std::uint32_t address) const = 0;
  virtual void write8(std::uint32_t address, std::uint8_t value) = 0;
  virtual void write32(std::uint32_t address, std::uint32_t value) = 0;

  virtual void commitPresentation() = 0;
  virtual void serviceAudioSink() = 0;
  virtual void servicePad() = 0;
};

// A mode body that outlived the field it started on.
struct StepState {
  bool modeCallPending = false;
  std::uint32_t buffer = 0;
};

// The three overridden entries and the field step, reproducing the guest bodies they replace.
class FiniteFrame {
public:
  static constexpr std::uint32_t kMain = 0x80028BA0u;
  static constexpr std::uint32_t kFrameBarrier = 0x800296C4u;
  static constexpr std::uint32_t kDisplayInit = 0x800B0954u;

  static void runBootPrefix(Machine &machine);
  [[nodiscard]] static bool runBarrier(Machine &machine);
  static void runDisplayInit(Machine &machine);
  static void step(Machine &machine, StepState &state);
};

class FrameDriver final : public ::FrameDriver {
public:
  explicit FrameDriver(Game &game);

  void installOverrides();
  void runBootPrefix(Core &core, std::uint32_t programEntry);
  void stepFrame(Core &core, std::uint32_t frame) override;

private:
  static FrameDriver &from(Core &core);
  static void mainOverride(Core *core);
  static void barrierOverride(Core *core);
  static void displayInitOverride(Core *core);

  Game &game_;
  StepState stepState_;
  psx::cpu::ResumableGuestCall modeCall_;
  bool bootStarted_ = false;
  bool bootComplete_ = false;
};

} // namespace tekken3::frame
