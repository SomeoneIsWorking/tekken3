#pragma once

#include "game_runtime.h"
#include "guest_execution.h"

#include <cstdint>

class Game;

namespace tekken3 {

// Injectable machine boundary used by both the shipping Core adapter and focused sequence tests.
// Every operation below is a real part of the title-owned finite boot/frame implementation.
class FrameMachine {
public:
  virtual ~FrameMachine() = default;

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

struct FrameStepState {
  bool modeCallPending = false;
  std::uint32_t buffer = 0;
};

class FrameLoop {
public:
  static constexpr std::uint32_t kMain = 0x80028BA0u;
  static constexpr std::uint32_t kFrameBarrier = 0x800296C4u;
  static constexpr std::uint32_t kDisplayInit = 0x800B0954u;

  static void runFiniteMain(FrameMachine &machine);
  [[nodiscard]] static bool runFrameBarrier(FrameMachine &machine);
  static void runDisplayInit(FrameMachine &machine);
  static void step(FrameMachine &machine, FrameStepState &state);
};

class Tekken3FrameDriver final : public FrameDriver {
public:
  explicit Tekken3FrameDriver(Game &game);

  void installOverrides();
  void runBootPrefix(Core &core, std::uint32_t programEntry);
  void stepFrame(Core &core, std::uint32_t frame) override;

private:
  static Tekken3FrameDriver &from(Core &core);
  static void mainOverride(Core *core);
  static void frameBarrierOverride(Core *core);
  static void displayInitOverride(Core *core);

  Game &game_;
  FrameStepState frameStep_;
  guest::BoundedCall modeCall_;
  bool bootStarted_ = false;
  bool bootComplete_ = false;
};

} // namespace tekken3
