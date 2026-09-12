#include "decompressor_probe.h"

#include "core.h"

#include <lucent/log.h>

#include <optional>

namespace tekken3 {
namespace {

constexpr std::uint32_t kDecompressorBegin = 0x80031BFCu;
constexpr std::uint32_t kDecompressorEnd = 0x80031CBCu;
constexpr std::uint32_t kOutputStartReady = 0x80031C0Cu;
constexpr std::uint32_t kCopyLoopBegin = 0x80031C78u;
constexpr std::uint32_t kCopyLoopEnd = 0x80031C94u;

std::optional<std::uint32_t> mappedByte(Core &core, std::uint32_t address) {
  auto range = core.mappedMainRamRange(address, 1);
  if (!range) {
    return std::nullopt;
  }
  return range->begin;
}

std::string mappedAddress(Core &core, std::uint32_t address) {
  auto offset = mappedByte(core, address);
  return offset ? lucent::format("0x{:08X}(RAM+0x{:06X})", address, *offset)
                : lucent::format("0x{:08X}(unmapped-main-RAM)", address);
}

} // namespace

GuestCallEntry DecompressorProbe::captureEntry(const Core &core, std::uint32_t address) {
  return {address, core.r[31], {core.r[4], core.r[5], core.r[6], core.r[7], core.r[9]}};
}

std::string DecompressorProbe::describe(Core &core, GuestCallEntry entry, const psx::cpu::ExecutionResult &result) {
  auto prefix = lucent::format("guest_call=0x{:08X} return=0x{:08X} entry[a0=0x{:08X} a1=0x{:08X} a2=0x{:08X} "
                               "a3=0x{:08X} t1=0x{:08X}] exit={} pc=0x{:08X} cycles={} decompressor_at_exit={}/1",
                               entry.address,
                               entry.returnPc,
                               entry.arguments[0],
                               entry.arguments[1],
                               entry.arguments[2],
                               entry.arguments[3],
                               entry.arguments[4],
                               psx::cpu::executionExitName(result.reason),
                               result.guestPc,
                               result.cycles,
                               result.guestPc >= kDecompressorBegin && result.guestPc < kDecompressorEnd ? 1 : 0);
  if (result.guestPc < kDecompressorBegin || result.guestPc >= kDecompressorEnd) {
    return prefix + " live_lz=unreached-at-exit; nested earlier calls are not observed";
  }

  auto source = core.r[4];
  auto destination = core.r[5];
  auto length = core.r[6];
  auto backReference = core.r[7];
  auto outputStart = core.r[9];
  auto outputStartOffset = mappedByte(core, outputStart);
  auto destinationOffset = mappedByte(core, destination);
  auto outputProgress = std::string{"unknown"};
  if (result.guestPc >= kOutputStartReady && outputStartOffset && destinationOffset && destination >= outputStart &&
      *destinationOffset >= *outputStartOffset &&
      destination - outputStart == *destinationOffset - *outputStartOffset) {
    outputProgress = lucent::format("{}/{} bytes within mapped main RAM",
                                    *destinationOffset - *outputStartOffset,
                                    sizeof(core.ram) - *outputStartOffset);
  }

  auto copyProgress = std::string{"not-at-copy-loop"};
  if (result.guestPc >= kCopyLoopBegin && result.guestPc < kCopyLoopEnd) {
    auto copied = core.r[3];
    auto destinationByte = mappedByte(core, destination);
    auto backReferenceByte = mappedByte(core, backReference);
    auto distanceValid = destinationByte && backReferenceByte && *destinationByte >= *backReferenceByte &&
                         *destinationByte - *backReferenceByte <= 2048u;
    auto distance = destinationByte && backReferenceByte && *destinationByte >= *backReferenceByte
                        ? lucent::format("{}", *destinationByte - *backReferenceByte)
                        : std::string{"unknown"};
    copyProgress = lucent::format("copied={}/{} count_within_length={} length_in_1..32={} "
                                  "backref_distance={}/2048 bounded={}",
                                  copied,
                                  length,
                                  copied <= length ? 1 : 0,
                                  length >= 1u && length <= 32u ? 1 : 0,
                                  distance,
                                  distanceValid ? 1 : 0);
  }

  return prefix + lucent::format(" live_lz[ra=0x{:08X} a0/source={} a1/destination={} a2/length={} "
                                 "a3/backref={} t1/output_start={}] source_progress=unknown(no-lz-entry-sample) "
                                 "output_progress={} copy_progress={}",
                                 core.r[31],
                                 mappedAddress(core, source),
                                 mappedAddress(core, destination),
                                 length,
                                 mappedAddress(core, backReference),
                                 mappedAddress(core, outputStart),
                                 outputProgress,
                                 copyProgress);
}

} // namespace tekken3
