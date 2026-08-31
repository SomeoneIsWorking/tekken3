#include "gpu_sync.h"

#include <cstdint>
#include <cstdio>
#include <unordered_map>

namespace {

constexpr std::uint32_t kGpuDataPointer = 0x80098C90u;
constexpr std::uint32_t kDmaControlPointer = 0x80098C94u;
constexpr std::uint32_t kGpuControlPointer = 0x80098C9Cu;
constexpr std::uint32_t kDmaChannelPointer = 0x80098CACu;
constexpr std::uint32_t kQueueHead = 0x80098CB0u;
constexpr std::uint32_t kQueueTail = 0x80098CB4u;
constexpr std::uint32_t kSavedCriticalSection = 0x80098CC0u;
constexpr std::uint32_t kFieldDeadline = 0x80098CC4u;
constexpr std::uint32_t kPollCount = 0x80098CC8u;

constexpr std::uint32_t kGpuData = 0x1F801810u;
constexpr std::uint32_t kGpuControl = 0x1F801814u;
constexpr std::uint32_t kDmaControl = 0x1F8010F0u;
constexpr std::uint32_t kDmaChannel = 0x1F8010A8u;

class RecordingGpuSyncMachine final : public tekken3::GpuSyncMachine {
public:
  RecordingGpuSyncMachine() {
    words[kGpuDataPointer] = kGpuData;
    words[kGpuControlPointer] = kGpuControl;
    words[kDmaControlPointer] = kDmaControl;
    words[kDmaChannelPointer] = kDmaChannel;
  }

  std::uint32_t fieldCounter() const override {
    return field;
  }

  std::uint32_t read32(std::uint32_t address) const override {
    const auto found = words.find(address);
    return found == words.end() ? 0 : found->second;
  }

  void write32(std::uint32_t address, std::uint32_t value) override {
    words[address] = value;
    if (address == kGpuData) {
      priorGpuDataWrite = lastGpuDataWrite;
      lastGpuDataWrite = value;
      ++gpuDataWrites;
    }
  }

  std::uint32_t setCriticalSection(std::uint32_t enabled, std::uint32_t returnPc) override {
    ++criticalCalls;
    if (criticalCalls == 1) {
      firstCriticalReturnPc = returnPc;
    } else {
      secondCriticalReturnPc = returnPc;
    }
    const std::uint32_t prior = critical;
    critical = enabled;
    return prior;
  }

  void reportTimeout(std::uint32_t queueDepth,
                     std::uint32_t gpuData,
                     std::uint32_t gpuControl,
                     std::uint32_t dmaControl) override {
    ++timeoutReports;
    reportedQueueDepth = queueDepth;
    reportedGpuData = gpuData;
    reportedGpuControl = gpuControl;
    reportedDmaControl = dmaControl;
  }

  std::unordered_map<std::uint32_t, std::uint32_t> words;
  std::uint32_t field = 0;
  std::uint32_t critical = 1;
  std::uint32_t criticalCalls = 0;
  std::uint32_t firstCriticalReturnPc = 0;
  std::uint32_t secondCriticalReturnPc = 0;
  std::uint32_t timeoutReports = 0;
  std::uint32_t reportedQueueDepth = 0;
  std::uint32_t reportedGpuData = 0;
  std::uint32_t reportedGpuControl = 0;
  std::uint32_t reportedDmaControl = 0;
  std::uint32_t gpuDataWrites = 0;
  std::uint32_t priorGpuDataWrite = 0;
  std::uint32_t lastGpuDataWrite = 0;
};

bool nativeFieldClockReplacesVsync() {
  RecordingGpuSyncMachine machine;
  machine.field = 41;
  tekken3::GpuSyncProtocol::arm(machine);
  if (machine.read32(kFieldDeadline) != 281 || machine.read32(kPollCount) != 0 ||
      tekken3::GpuSyncProtocol::poll(machine) != 0 || machine.read32(kPollCount) != 1 || machine.timeoutReports != 0 ||
      machine.criticalCalls != 0) {
    return false;
  }
  machine.field = 281;
  return tekken3::GpuSyncProtocol::poll(machine) == 0 && machine.timeoutReports == 0;
}

bool fieldTimeoutPreservesRetailReset() {
  RecordingGpuSyncMachine machine;
  machine.field = 5;
  tekken3::GpuSyncProtocol::arm(machine);
  machine.words[kQueueHead] = 70;
  machine.words[kQueueTail] = 3;
  machine.words[kGpuData] = 0x11111111u;
  machine.words[kGpuControl] = 0x22222222u;
  machine.words[kDmaControl] = 0x33333333u;
  machine.words[kDmaChannel] = 0x40u;
  machine.field = 246;

  return tekken3::GpuSyncProtocol::poll(machine) == -1 && machine.timeoutReports == 1 &&
         machine.reportedQueueDepth == 3 && machine.reportedGpuData == 0x11111111u &&
         machine.reportedGpuControl == 0x22222222u && machine.reportedDmaControl == 0x33333333u &&
         machine.read32(kQueueHead) == 0 && machine.read32(kQueueTail) == 0 &&
         machine.read32(kSavedCriticalSection) == 1 && machine.read32(kGpuControl) == 0x401u &&
         machine.read32(kDmaChannel) == 0x840u && machine.gpuDataWrites == 2 &&
         machine.priorGpuDataWrite == 0x02000000u && machine.lastGpuDataWrite == 0x01000000u &&
         machine.criticalCalls == 2 && machine.firstCriticalReturnPc == 0x8007E9D0u &&
         machine.secondCriticalReturnPc == 0x8007EA4Cu && machine.critical == 1;
}

bool pollCountStillDetectsAStalledQueue() {
  RecordingGpuSyncMachine machine;
  machine.field = 9;
  tekken3::GpuSyncProtocol::arm(machine);
  machine.words[kPollCount] = 0xF0001u;
  return tekken3::GpuSyncProtocol::poll(machine) == -1 && machine.timeoutReports == 1 &&
         machine.read32(kPollCount) == 0xF0002u;
}

} // namespace

int main() {
  if (!nativeFieldClockReplacesVsync() || !fieldTimeoutPreservesRetailReset() ||
      !pollCountStillDetectsAStalledQueue()) {
    std::fprintf(stderr,
                 "gpu_sync_contract: FAIL — native field timing diverged from Tekken's measured GPU "
                 "queue timeout/reset contract\n");
    return 1;
  }
  std::printf("gpu_sync_contract: PASS — GPU queue arm/poll use the native field clock, retain the "
              "poll-count failsafe and exact reset sequence, and expose no guest VSync path\n");
  return 0;
}
