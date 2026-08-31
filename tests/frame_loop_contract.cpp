#include "frame_loop.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

struct Operation {
  std::string kind;
  std::uint32_t address = 0;
  std::uint32_t returnPc = 0;
  std::uint32_t a0 = 0;
  std::uint32_t a1 = 0;
  std::uint32_t a2 = 0;
};

class RecordingMachine final : public tekken3::FrameMachine {
public:
  void call(std::uint32_t address, std::uint32_t returnPc) override {
    operations.push_back({"call", address, returnPc});
    result = callResults[address];
  }

  void call1(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0) override {
    operations.push_back({"call1", address, returnPc, a0});
    result = callResults[address];
  }

  void
  call3(std::uint32_t address, std::uint32_t returnPc, std::uint32_t a0, std::uint32_t a1, std::uint32_t a2) override {
    operations.push_back({"call3", address, returnPc, a0, a1, a2});
    result = callResults[address];
  }

  void deliverEvent(std::uint32_t eventClass, std::uint32_t spec) override {
    operations.push_back({"event", eventClass, spec});
    if (releaseFrameEvent) {
      memory[0x8009BC5Cu] = 1;
    }
  }

  std::uint32_t returnValue() const override {
    return result;
  }

  std::uint32_t readRegister(std::uint32_t index) const override {
    return registers[index];
  }

  void writeRegister(std::uint32_t index, std::uint32_t value) override {
    registers[index] = value;
  }

  void tick(std::uint32_t guestInstructions) override {
    guestTicks += guestInstructions;
  }

  std::uint8_t read8(std::uint32_t address) const override {
    return static_cast<std::uint8_t>(read32(address));
  }

  std::uint16_t read16(std::uint32_t address) const override {
    return static_cast<std::uint16_t>(read32(address));
  }

  std::uint32_t read32(std::uint32_t address) const override {
    const auto found = memory.find(address);
    return found == memory.end() ? 0 : found->second;
  }

  void write8(std::uint32_t address, std::uint8_t value) override {
    memory[address] = value;
    operations.push_back({"write8", address, 0, value});
  }

  void write32(std::uint32_t address, std::uint32_t value) override {
    memory[address] = value;
    operations.push_back({"write32", address, 0, value});
  }

  void commitPresentation() override {
    operations.push_back({"present"});
  }

  void serviceAudioSink() override {
    operations.push_back({"audio"});
  }

  void servicePad() override {
    operations.push_back({"pad"});
  }

  std::vector<Operation> operations;
  std::unordered_map<std::uint32_t, std::uint32_t> memory;
  std::unordered_map<std::uint32_t, std::uint32_t> callResults;
  std::array<std::uint32_t, 32> registers{};
  std::uint32_t guestTicks = 0;
  std::uint32_t result = 0;
  bool releaseFrameEvent = true;
};

bool operationIs(const Operation &operation, const char *kind, std::uint32_t address = 0, std::uint32_t returnPc = 0) {
  return operation.kind == kind && operation.address == address && operation.returnPc == returnPc;
}

bool finiteBootIsOrdered() {
  RecordingMachine machine;
  machine.registers[16] = 0x16161616u;
  machine.registers[17] = 0x17171717u;
  machine.registers[18] = 0x18181818u;
  machine.registers[29] = 0x00010000u;
  machine.registers[31] = 0x31313131u;
  tekken3::FrameLoop::runFiniteMain(machine);
  return machine.operations.size() == 6 && operationIs(machine.operations[4], "call", 0x80079D10u, 0x80028BB8u) &&
         operationIs(machine.operations[5], "call", 0x800B0548u, 0x80028BC0u) && machine.registers[29] == 0x0000FFE0u &&
         machine.memory[0x0000FFFCu] == 0x31313131u && machine.memory[0x0000FFF8u] == 0x18181818u &&
         machine.memory[0x0000FFF4u] == 0x17171717u && machine.memory[0x0000FFF0u] == 0x16161616u &&
         machine.registers[16] == 0x800B0000u && machine.registers[17] == 0x800B0000u &&
         machine.registers[18] == 0x800AE040u && machine.registers[2] == 0x800B0000u && machine.guestTicks == 11;
}

bool displayInitOmitsOnlyVsync() {
  RecordingMachine machine;
  machine.registers[29] = 0x00010000u;
  machine.registers[31] = 0x31313131u;
  tekken3::FrameLoop::runDisplayInit(machine);
  if (machine.operations.size() != 7 || !operationIs(machine.operations[1], "call1", 0x8007AED8u, 0x800B096Cu) ||
      machine.operations[1].a0 != 0 || !operationIs(machine.operations[2], "call", 0x8007AF44u, 0x800B0974u) ||
      !operationIs(machine.operations[3], "call", 0x80079E08u, 0x800B097Cu) ||
      !operationIs(machine.operations[4], "call", 0x800B09A0u, 0x800B0984u)) {
    return false;
  }
  for (const Operation &operation : machine.operations) {
    if (operation.address == 0x800859A8u) {
      return false;
    }
  }
  return machine.memory[0x800ADF60u] == 0 && machine.memory[0x800ADF61u] == 0 && machine.registers[29] == 0x00010000u &&
         machine.registers[31] == 0x31313131u && machine.registers[2] == 0x800ADF40u && machine.guestTicks == 19;
}

bool frameBarrierKeepsBothConditionalAnswers() {
  RecordingMachine enabled;
  enabled.memory[0x8009542Cu] = 1;
  enabled.memory[0x800A8C54u] = 0x800A85A4u;
  enabled.memory[0x800A912Cu] = 6;
  enabled.registers[16] = 0x16161616u;
  enabled.registers[17] = 0x17171717u;
  enabled.registers[29] = 0x00010000u;
  enabled.registers[31] = 0x31313131u;
  const bool enabledReleased = tekken3::FrameLoop::runFrameBarrier(enabled);
  if (enabled.operations.size() != 13 || !operationIs(enabled.operations[4], "call1", 0x80029924u, 0x800296E4u) ||
      enabled.operations[4].a0 != 1 || !operationIs(enabled.operations[5], "call", 0x80029A28u, 0x80029700u) ||
      !operationIs(enabled.operations[8], "call", 0x8004CE54u, 0x80029728u) || enabled.operations[10].kind != "pad" ||
      !operationIs(enabled.operations[11], "event", 0xF2000002u, 0x00000002u) ||
      enabled.memory[0x8009BC60u] != 0x800A85A4u || enabled.memory[0x800A912Cu] != 7u * 0x10DCDu ||
      enabled.memory[0x800ADCA4u] != 0 || enabled.registers[29] != 0x00010000u ||
      enabled.registers[31] != 0x31313131u || enabled.registers[16] != 0x16161616u ||
      enabled.registers[17] != 0x17171717u || enabled.registers[2] != 0x800B0000u || enabled.guestTicks != 48 ||
      !enabledReleased) {
    return false;
  }

  RecordingMachine disabled;
  disabled.registers[29] = 0x00010000u;
  disabled.memory[0x8009542Cu] = 0;
  disabled.memory[0x8009BC60u] = 0x12345678u;
  const bool disabledReleased = tekken3::FrameLoop::runFrameBarrier(disabled);
  for (const Operation &operation : disabled.operations) {
    if (operation.address == 0x80029A28u) {
      return false;
    }
  }
  if (disabled.memory[0x8009BC60u] != 0x12345678u || disabled.guestTicks != 41 || !disabledReleased) {
    return false;
  }

  RecordingMachine missingEvent;
  missingEvent.registers[29] = 0x00010000u;
  missingEvent.releaseFrameEvent = false;
  return !tekken3::FrameLoop::runFrameBarrier(missingEvent);
}

bool frameStepKeepsServiceAndRenderOrder() {
  RecordingMachine machine;
  machine.memory[0x800AFA4Cu] = 9;
  machine.memory[0x800ADEFCu] = 1;
  machine.memory[0x800AE204u] = 3;
  machine.memory[0x800AE05Cu] = 0x80091234u;
  machine.memory[0x800A85A8u] = 0x80070000u;
  machine.memory[0x800A9218u] = 0x80062000u;
  machine.memory[0x800ADD54u] = 0x80063000u;
  machine.callResults[0x80029628u] = 0;
  machine.callResults[0x80080D98u] = 1;
  tekken3::FrameLoop::step(machine);

  if (machine.operations.size() != 15 || !operationIs(machine.operations[0], "call", 0x800296C4u, 0x80028BD4u) ||
      machine.operations[1].kind != "present" || machine.operations[2].kind != "audio" ||
      !operationIs(machine.operations[3], "call", 0x8006B6FCu, 0x80028BDCu) ||
      !operationIs(machine.operations[5], "call", 0x80029628u, 0x80028BF4u) ||
      !operationIs(machine.operations[6], "call", 0x80080D98u, 0x80028C04u) ||
      !operationIs(machine.operations[9], "call1", 0x80081C38u, 0x80028C44u) ||
      machine.operations[9].a0 != 0x80091234u ||
      !operationIs(machine.operations[10], "call3", 0x800817F8u, 0x80028C54u) ||
      !operationIs(machine.operations[11], "call1", 0x8004C684u, 0x80028C60u) ||
      !operationIs(machine.operations[12], "call", 0x800DB1B8u, 0x80028CCCu) ||
      !operationIs(machine.operations[13], "call3", 0x8007BAB0u, 0x80028DECu) ||
      machine.operations[13].a0 != 0x80070020u || machine.operations[13].a1 != 0x80062000u ||
      machine.operations[13].a2 != 0x80062020u ||
      !operationIs(machine.operations[14], "call3", 0x8007BAB0u, 0x80028E0Cu) ||
      machine.operations[14].a0 != 0x80070FB8u || machine.operations[14].a1 != 0x80063000u ||
      machine.operations[14].a2 != 0x80063020u) {
    return false;
  }
  return machine.memory[0x800AFA4Cu] == 10 && machine.memory[0x800A8C54u] == 0x800A85A4u &&
         machine.registers[2] == 0x800B0000u && machine.guestTicks == 71;
}

} // namespace

int main() {
  if (!finiteBootIsOrdered() || !displayInitOmitsOnlyVsync() || !frameBarrierKeepsBothConditionalAnswers() ||
      !frameStepKeepsServiceAndRenderOrder()) {
    std::fprintf(stderr,
                 "frame_loop_contract: FAIL — finite boot/frame sequence diverged from the "
                 "measured title contract\n");
    return 1;
  }
  std::printf("frame_loop_contract: PASS — finite boot 2/2, display init 6/6, frame barrier "
              "enabled+disabled, and ordered presentation/audio/pad/CD/render contracts hold\n");
  return 0;
}
