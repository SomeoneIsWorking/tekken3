#include "fieldclock/field_clock.h"
#include "render/gpu_queue_timeout.h"

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

class RecordingQueueMachine final : public tekken3::render::QueueMachine {
public:
  RecordingQueueMachine() {
    words[kGpuDataPointer] = kGpuData;
    words[kGpuControlPointer] = kGpuControl;
    words[kDmaControlPointer] = kDmaControl;
    words[kDmaChannelPointer] = kDmaChannel;
  }

  // Served from the word map at the production counter address, not a separate member.
  std::uint32_t fieldCounter() const override {
    return read32(tekken3::field::kCounter);
  }

  void setFieldCounter(std::uint32_t value) {
    words[tekken3::field::kCounter] = value;
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

bool guestFieldWordArmsTheDeadline() {
  RecordingQueueMachine machine;
  machine.setFieldCounter(41);
  tekken3::render::armDeadline(machine);
  if (machine.read32(kFieldDeadline) != 281 || machine.read32(kPollCount) != 0 ||
      tekken3::render::pollQueue(machine) != 0 || machine.read32(kPollCount) != 1 || machine.timeoutReports != 0 ||
      machine.criticalCalls != 0) {
    return false;
  }
  machine.setFieldCounter(281);
  return tekken3::render::pollQueue(machine) == 0 && machine.timeoutReports == 0;
}

bool fieldTimeoutPreservesRetailReset() {
  RecordingQueueMachine machine;
  machine.setFieldCounter(5);
  tekken3::render::armDeadline(machine);
  machine.words[kQueueHead] = 70;
  machine.words[kQueueTail] = 3;
  machine.words[kGpuData] = 0x11111111u;
  machine.words[kGpuControl] = 0x22222222u;
  machine.words[kDmaControl] = 0x33333333u;
  machine.words[kDmaChannel] = 0x40u;
  machine.setFieldCounter(246);

  return tekken3::render::pollQueue(machine) == -1 && machine.timeoutReports == 1 && machine.reportedQueueDepth == 3 &&
         machine.reportedGpuData == 0x11111111u && machine.reportedGpuControl == 0x22222222u &&
         machine.reportedDmaControl == 0x33333333u && machine.read32(kQueueHead) == 0 &&
         machine.read32(kQueueTail) == 0 && machine.read32(kSavedCriticalSection) == 1 &&
         machine.read32(kGpuControl) == 0x401u && machine.read32(kDmaChannel) == 0x840u && machine.gpuDataWrites == 2 &&
         machine.priorGpuDataWrite == 0x02000000u && machine.lastGpuDataWrite == 0x01000000u &&
         machine.criticalCalls == 2 && machine.firstCriticalReturnPc == 0x8007E9D0u &&
         machine.secondCriticalReturnPc == 0x8007EA4Cu && machine.critical == 1;
}

bool pollCountStillDetectsAStalledQueue() {
  RecordingQueueMachine machine;
  machine.setFieldCounter(9);
  tekken3::render::armDeadline(machine);
  machine.words[kPollCount] = 0xF0001u;
  return tekken3::render::pollQueue(machine) == -1 && machine.timeoutReports == 1 &&
         machine.read32(kPollCount) == 0xF0002u;
}

// A frozen guest field word (deadline 0xF0) never expires; advancing the guest word does.
bool aFrozenGuestFieldWordNeverExpiresTheDeadline() {
  RecordingQueueMachine machine;
  machine.setFieldCounter(0);
  tekken3::render::armDeadline(machine);
  if (machine.read32(kFieldDeadline) != 0xF0u) {
    return false;
  }
  for (int field = 0; field < 1000; ++field) {
    if (tekken3::render::pollQueue(machine) != 0) {
      return false;
    }
  }
  machine.setFieldCounter(240);
  return tekken3::render::pollQueue(machine) == 0;
}

} // namespace

int main() {
  if (!guestFieldWordArmsTheDeadline() || !fieldTimeoutPreservesRetailReset() ||
      !pollCountStillDetectsAStalledQueue() || !aFrozenGuestFieldWordNeverExpiresTheDeadline()) {
    std::fprintf(stderr,
                 "gpu_sync_contract: FAIL — GPU queue timeout diverged from Tekken's measured "
                 "guest-field-word arm/poll/reset contract\n");
    return 1;
  }
  std::printf("gpu_sync_contract: PASS — 4/4 cases: the deadline is armed from the guest's own VSync "
              "field word (41 -> 281, and a frozen 0 word cannot expire it), the poll-count failsafe "
              "still fires, and the retail reset sequence and both critical-section return PCs are "
              "exact. No host counter and no guest VSync call take part\n");
  return 0;
}
