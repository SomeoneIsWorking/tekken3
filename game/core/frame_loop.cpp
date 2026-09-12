#include "frame_loop.h"

#include "core.h"
#include "execution_control.h"
#include "execution_services.h"
#include "game.h"
#include "guest_execution.h"
#include "native_dispatch.h"

#include <array>
#include <cstddef>
#include <cstdlib>
#include <lucent/log.h>

namespace tekken3 {
namespace {

constexpr std::uint32_t kFirstInitializer = 0x80079D10u;
constexpr std::uint32_t kSecondInitializer = 0x800B0548u;
constexpr std::uint32_t kFrameTimerEventClass = 0xF2000002u;
constexpr std::uint32_t kFrameTimerEventSpec = 0x00000002u;
constexpr std::uint32_t kFrameTimerSnapshot = 0x80029924u;
constexpr std::uint32_t kCompactOrderingTables = 0x80029A28u;
constexpr std::uint32_t kAdvanceWaitPrng = 0x8004CE54u;
constexpr std::uint32_t kCdXaState = 0x8006B6FCu;
constexpr std::uint32_t kRenderModeQuery = 0x80029628u;
constexpr std::uint32_t kSelectBuffer = 0x80080D98u;
constexpr std::uint32_t kSelectGeometry = 0x80081C38u;
constexpr std::uint32_t kClearMainOt = 0x800817F8u;
constexpr std::uint32_t kSelectOtRoots = 0x8004C684u;
constexpr std::uint32_t kSpliceOt = 0x8007BAB0u;

constexpr std::uint32_t kDisplayReset = 0x8007AED8u;
constexpr std::uint32_t kDisplayResetTail = 0x8007AF44u;
constexpr std::uint32_t kEventReset = 0x80079E08u;
constexpr std::uint32_t kDisplayEventInit = 0x800B09A0u;

constexpr std::uint32_t kFrameTimerEnabled = 0x8009542Cu;
constexpr std::uint32_t kFrameWaitDepth = 0x80095428u;
constexpr std::uint32_t kFrameEventCount = 0x8009BC5Cu;
constexpr std::uint32_t kPriorBuffer = 0x8009BC60u;
constexpr std::uint32_t kCurrentBuffer = 0x800A8C54u;
constexpr std::uint32_t kWaitPrng = 0x800A912Cu;
constexpr std::uint32_t kFrameCounter = 0x800AFA4Cu;
constexpr std::uint32_t kActiveBufferIndex = 0x800ADEFCu;
constexpr std::uint32_t kRenderMode = 0x800AE204u;
constexpr std::uint32_t kCallbackRenderGuard = 0x800ADCA4u;
constexpr std::uint32_t kDisplayEventBase = 0x800ADF40u;
constexpr std::uint32_t kBufferDescriptors = 0x800A8590u;
constexpr std::uint32_t kGeometryStates = 0x800AE040u;
constexpr std::uint32_t kMainOtRoot = 0x800A9218u;
constexpr std::uint32_t kSecondaryOtRoot = 0x800ADD54u;

constexpr std::uint32_t kWaitPrngMultiplier = 0x00010DCDu;

constexpr std::uint32_t kV0 = 2;
constexpr std::uint32_t kS0 = 16;
constexpr std::uint32_t kS1 = 17;
constexpr std::uint32_t kS2 = 18;
constexpr std::uint32_t kSp = 29;
constexpr std::uint32_t kRa = 31;

constexpr std::array<std::uint32_t, 20> kModeFunctions{
    0x800B0708u, 0x80052CC4u, 0x8004FA60u, 0x800DB1B8u, 0x800DB5B4u, 0x800DDE64u, 0x800D3228u,
    0x80050318u, 0x80050428u, 0x8010FF4Cu, 0x80055590u, 0x80052520u, 0x800EEE8Cu, 0x800EF92Cu,
    0x800F0458u, 0x800F18E8u, 0x800501C0u, 0x800C2434u, 0x8004FF74u, 0x800FF0C4u,
};

class CoreFrameMachine final : public FrameMachine {
public:
  CoreFrameMachine(Game &game, Core &core, guest::BoundedCall &modeCall)
      : game_(game), core_(core), modeCall_(modeCall) {}

  void call(std::uint32_t address, std::uint32_t returnPc) override {
    core_.r[31] = returnPc;
    guest::call(core_, address, "Tekken3 frame guest call");
  }

  void call1(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0) override {
    core_.r[4] = a0;
    call(address, returnPc);
  }

  void
  call3(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1, std::uint32_t a2) override {
    core_.r[4] = a0;
    core_.r[5] = a1;
    core_.r[6] = a2;
    call(address, returnPc);
  }

  bool startModeCall(std::uint32_t address, std::uint32_t returnPc) override {
    return modeCall_.start(
        core_, address, returnPc, "Tekken3 frame mode call", psx::cpu::ExecutionBudget::currentTurn(core_));
  }

  bool resumeModeCall() override {
    return modeCall_.resume(core_, "Tekken3 frame mode call", psx::cpu::ExecutionBudget::currentTurn(core_));
  }

  void deliverEvent(std::uint32_t eventClass, std::uint32_t spec) override {
    game_.hle.deliverEvent(eventClass, spec);
  }

  std::uint32_t returnValue() const override {
    return core_.r[2];
  }

  std::uint32_t readRegister(std::uint32_t index) const override {
    return core_.r[index];
  }

  void writeRegister(std::uint32_t index, std::uint32_t value) override {
    core_.r[index] = value;
  }

  void tick(std::uint32_t guestInstructions) override {
    psx::cpu::accountGuestInstructions(core_, guestInstructions);
  }

  std::uint8_t read8(std::uint32_t address) const override {
    return core_.mem_r8(address);
  }

  std::uint16_t read16(std::uint32_t address) const override {
    return core_.mem_r16(address);
  }

  std::uint32_t read32(std::uint32_t address) const override {
    return core_.mem_r32(address);
  }

  void write8(std::uint32_t address, std::uint8_t value) override {
    core_.mem_w8(address, value);
  }

  void write32(std::uint32_t address, std::uint32_t value) override {
    core_.mem_w32(address, value);
  }

  void commitPresentation() override {
    game_.presentation.commit(&core_, 1, game_.temporalPresentation.get());
  }

  void serviceAudioSink() override {
    game_.spu_audio.frame();
  }

  void servicePad() override {
    game_.pad.serviceFrame();
  }

private:
  Game &game_;
  Core &core_;
  guest::BoundedCall &modeCall_;
};

void finishFrame(FrameMachine &machine, std::uint32_t buffer) {
  machine.writeRegister(kV0, 0x800B0000u);
  const std::uint32_t bufferPacketBase = machine.read32(buffer + 4u);
  const std::uint32_t mainOtRoot = machine.read32(kMainOtRoot);
  machine.tick(7);
  machine.call3(kSpliceOt, 0x80028DECu, bufferPacketBase + 0x20u, mainOtRoot, mainOtRoot + 0x20u);
  const std::uint32_t secondaryOtRoot = machine.read32(kSecondaryOtRoot);
  machine.tick(8);
  machine.call3(kSpliceOt, 0x80028E0Cu, bufferPacketBase + 0xFB8u, secondaryOtRoot, secondaryOtRoot + 0x20u);
  machine.tick(2);
}

} // namespace

void FrameLoop::runFiniteMain(FrameMachine &machine) {
  // Exact non-returning 0x80028BA0 prologue. This frame remains resident for every host-driven
  // iteration, just as it does around the retail loop back-edge.
  const std::uint32_t stack = machine.readRegister(kSp) - 32u;
  machine.writeRegister(kSp, stack);
  machine.write32(stack + 28u, machine.readRegister(kRa));
  machine.write32(stack + 24u, machine.readRegister(kS2));
  machine.write32(stack + 20u, machine.readRegister(kS1));
  machine.write32(stack + 16u, machine.readRegister(kS0));
  machine.tick(6);
  machine.call(kFirstInitializer, 0x80028BB8u);
  machine.writeRegister(kS1, 0x800B0000u);
  machine.tick(2);
  machine.call(kSecondInitializer, 0x80028BC0u);
  machine.writeRegister(kS0, 0x800B0000u);
  machine.writeRegister(kV0, 0x800B0000u);
  machine.writeRegister(kS2, 0x800AE040u);
  machine.tick(3);
}

bool FrameLoop::runFrameBarrier(FrameMachine &machine) {
  const std::uint32_t stack = machine.readRegister(kSp) - 32u;
  machine.writeRegister(kSp, stack);
  machine.write32(stack + 24u, machine.readRegister(kRa));
  machine.write32(stack + 20u, machine.readRegister(kS1));
  machine.write32(stack + 16u, machine.readRegister(kS0));

  machine.write32(kFrameWaitDepth, 0);
  machine.tick(8);
  machine.call1(kFrameTimerSnapshot, 0x800296E4u, 1);
  machine.tick(5);
  if (machine.read32(kFrameTimerEnabled) != 0) {
    machine.tick(2);
    machine.call(kCompactOrderingTables, 0x80029700u);
    machine.write32(kPriorBuffer, machine.read32(kCurrentBuffer));
    machine.tick(5);
  }

  machine.write32(kFrameEventCount, 0);
  machine.writeRegister(kS0, 0x800B0000u);
  machine.writeRegister(kS1, 0x800A0000u);
  machine.tick(3);
  // A native frame-shell turn owns exactly one RCntCNT2 delivery. This replaces the unbounded
  // hardware wait while retaining the wait body's one guaranteed PRNG iteration and accumulator
  // update before the delivered callback releases the barrier.
  machine.tick(2);
  machine.call(kAdvanceWaitPrng, 0x80029728u);
  machine.write32(kWaitPrng, (machine.read32(kWaitPrng) + 1u) * kWaitPrngMultiplier);
  machine.tick(15);
  // On hardware, linked libpad has filled these receive buffers before the CNT2 callback parses
  // them. Publish the finalized host packet here so the retained 0x800291D8/0x80029DC0 calls consume
  // this frame's input rather than a stale or permanently disconnected packet.
  machine.servicePad();
  // 0x80029894 registers the RCntCNT2 event as EvMdINTR. Route the finite host-owned turn through
  // the shipping BIOS event owner so open/enabled state, callback dispatch, register preservation,
  // and nested-delivery policy remain authoritative in one place.
  machine.deliverEvent(kFrameTimerEventClass, kFrameTimerEventSpec);
  const bool released = machine.read32(kFrameEventCount) != 0;
  machine.write32(kCallbackRenderGuard, 0);

  machine.writeRegister(kV0, 0x800B0000u);
  machine.writeRegister(kRa, machine.read32(stack + 24u));
  machine.writeRegister(kS1, machine.read32(stack + 20u));
  machine.writeRegister(kS0, machine.read32(stack + 16u));
  machine.writeRegister(kSp, stack + 32u);
  machine.tick(8);
  return released;
}

void FrameLoop::runDisplayInit(FrameMachine &machine) {
  const std::uint32_t stack = machine.readRegister(kSp) - 24u;
  machine.writeRegister(kSp, stack);
  machine.write32(stack + 16u, machine.readRegister(kRa));

  // Exact 0x800B0954 body except for its leading VSync(0). Native frame ownership has already been
  // established before boot, so calling guest VSync here would be a fatal second cadence owner.
  machine.tick(4);
  machine.tick(2);
  machine.call1(kDisplayReset, 0x800B096Cu, 0);
  machine.tick(2);
  machine.call(kDisplayResetTail, 0x800B0974u);
  machine.tick(2);
  machine.call(kEventReset, 0x800B097Cu);
  machine.tick(2);
  machine.call(kDisplayEventInit, 0x800B0984u);
  machine.write8(kDisplayEventBase + 0x20u, 0);
  machine.write8(kDisplayEventBase + 0x21u, 0);

  machine.writeRegister(kV0, kDisplayEventBase);
  machine.writeRegister(kRa, machine.read32(stack + 16u));
  machine.writeRegister(kSp, stack + 24u);
  machine.tick(7);
}

void FrameLoop::step(FrameMachine &machine, FrameStepState &state) {
  if (state.modeCallPending) {
    // The guest has not reached the next frame barrier. The display repeats its held image and
    // the audio sink advances for this field, while the guest CPU resumes the same call state.
    machine.servicePad();
    machine.commitPresentation();
    machine.serviceAudioSink();
    if (!machine.resumeModeCall()) {
      return;
    }
    state.modeCallPending = false;
    machine.tick(2);
    finishFrame(machine, state.buffer);
    return;
  }
  // The callback delivered by the barrier consumes the already-published pad packet after it submits
  // the prior buffer and advances guest sound. Commit those guest presentation/audio products in
  // the same order after the complete interrupt-context callback returns.
  machine.tick(2);
  machine.call(kFrameBarrier, 0x80028BD4u);
  machine.commitPresentation();
  machine.serviceAudioSink();

  machine.tick(2);
  machine.call(kCdXaState, 0x80028BDCu);
  machine.write32(kFrameCounter, machine.read32(kFrameCounter) + 1u);
  machine.tick(6);
  machine.call(kRenderModeQuery, 0x80028BF4u);
  machine.tick(2);
  if (machine.returnValue() == 0) {
    machine.tick(2);
    machine.call(kSelectBuffer, 0x80028C04u);
    machine.write32(kActiveBufferIndex, machine.returnValue());
    machine.tick(1);
  }

  const std::uint32_t bufferIndex = machine.read32(kActiveBufferIndex);
  const std::uint32_t buffer = kBufferDescriptors + bufferIndex * 20u;
  machine.write32(kCurrentBuffer, buffer);
  machine.tick(15);
  machine.call1(kSelectGeometry, 0x80028C44u, machine.read32(kGeometryStates + bufferIndex * 28u));
  machine.tick(4);
  machine.call3(kClearMainOt, 0x80028C54u, 0, 0, buffer);
  machine.tick(3);
  machine.call1(kSelectOtRoots, 0x80028C60u, bufferIndex);

  const std::int16_t mode = static_cast<std::int16_t>(machine.read16(kRenderMode));
  machine.tick(6);
  if (mode >= 0 && static_cast<std::size_t>(mode) < kModeFunctions.size()) {
    machine.tick(7);
    machine.tick(2);
    const auto address = kModeFunctions[static_cast<std::size_t>(mode)];
    const auto returnPc = 0x80028C9Cu + static_cast<std::uint32_t>(mode) * 0x10u;
    if (mode == 0) {
      state.buffer = buffer;
      if (!machine.startModeCall(address, returnPc)) {
        state.modeCallPending = true;
        return;
      }
    } else {
      machine.call(address, returnPc);
    }
    machine.tick(mode == 19 ? 1u : 2u);
  } else {
    machine.tick(1);
  }

  finishFrame(machine, buffer);
}

Tekken3FrameDriver::Tekken3FrameDriver(Game &game) : game_(game) {}

Tekken3FrameDriver &Tekken3FrameDriver::from(Core &core) {
  if (!core.game || !core.game->frameDriver) {
    lucent::error("frame", "Tekken 3 frame callback ran without its title FrameDriver");
    std::abort();
  }
  auto *const driver = dynamic_cast<Tekken3FrameDriver *>(core.game->frameDriver.get());
  if (!driver) {
    lucent::error("frame", "Tekken 3 frame callback reached another title's FrameDriver");
    std::abort();
  }
  return *driver;
}

void Tekken3FrameDriver::mainOverride(Core *core) {
  Tekken3FrameDriver &driver = from(*core);
  if (!driver.bootStarted_ || driver.bootComplete_) {
    lucent::error("boot", "Tekken 3 finite main reached outside its one boot dispatch");
    std::abort();
  }
  CoreFrameMachine machine(driver.game_, *core, driver.modeCall_);
  FrameLoop::runFiniteMain(machine);
  driver.bootComplete_ = true;
  psx::cpu::requestExecutionExit(*core, psx::cpu::ExecutionExitReason::HostService);
}

void Tekken3FrameDriver::frameBarrierOverride(Core *core) {
  Tekken3FrameDriver &driver = from(*core);
  CoreFrameMachine machine(driver.game_, *core, driver.modeCall_);
  if (!FrameLoop::runFrameBarrier(machine)) {
    lucent::error("frame",
                  "Tekken 3 RCntCNT2 event class 0x{:08X} spec 0x{:08X} did not release the frame barrier",
                  kFrameTimerEventClass,
                  kFrameTimerEventSpec);
    std::abort();
  }
}

void Tekken3FrameDriver::displayInitOverride(Core *core) {
  Tekken3FrameDriver &driver = from(*core);
  CoreFrameMachine machine(driver.game_, *core, driver.modeCall_);
  FrameLoop::runDisplayInit(machine);
}

void Tekken3FrameDriver::installOverrides() {
  guest::install(game_.core, FrameLoop::kMain, "Tekken3::finiteMain", mainOverride);
  guest::install(game_.core, FrameLoop::kFrameBarrier, "Tekken3::frameBarrier", frameBarrierOverride);
  guest::install(game_.core, FrameLoop::kDisplayInit, "Tekken3::displayInit", displayInitOverride);
}

void Tekken3FrameDriver::runBootPrefix(Core &core, std::uint32_t programEntry) {
  if (bootStarted_) {
    lucent::error("boot", "Tekken 3 finite boot prefix was requested more than once");
    std::abort();
  }
  bootStarted_ = true;
  const auto result = psx::cpu::dispatchGuest(core, programEntry, psx::cpu::ExecutionBudget::currentTurn(core));
  if (result.reason != psx::cpu::ExecutionExitReason::HostService) {
    lucent::error("boot",
                  "Tekken 3 boot exited as {} at 0x{:08X}, expected finite-main host transfer",
                  psx::cpu::executionExitName(result.reason),
                  result.guestPc);
    std::abort();
  }
  if (!bootComplete_) {
    lucent::error("boot",
                  "Tekken 3 retail entry 0x{:08X} returned without reaching finite main 0x{:08X}",
                  programEntry,
                  FrameLoop::kMain);
    std::abort();
  }
  lucent::info("boot", "Tekken 3 finite main prefix complete; native driver owns loop 0x80028BCC");
}

void Tekken3FrameDriver::stepFrame(Core &core, std::uint32_t frame) {
  if (!bootComplete_) {
    lucent::error("frame", "Tekken 3 frame {} ran before its finite boot prefix", frame);
    std::abort();
  }
  if (frameStep_.modeCallPending != modeCall_.pending()) {
    lucent::error("frame", "Tekken 3 mode call and frame continuation disagree at field {}", frame);
    std::abort();
  }
  if (!frameStep_.modeCallPending) {
    game_.timing.logicFrame = frame;
    game_.core.rsub.otAttr.beginLogicFrame(frame);
  }
  CoreFrameMachine machine(game_, core, modeCall_);
  FrameLoop::step(machine, frameStep_);
}

} // namespace tekken3
