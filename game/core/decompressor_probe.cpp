#include "decompressor_probe.h"

#include "core.h"

#include <lucent/log.h>

#include <cstddef>
#include <limits>
#include <optional>

namespace tekken3 {
namespace {

constexpr std::uint32_t kDecompressorBegin = 0x80031BFCu;
constexpr std::uint32_t kDecompressorEnd = 0x80031CBCu;
constexpr std::uint32_t kOutputStartReady = 0x80031C0Cu;
constexpr std::uint32_t kCopyLoopBegin = 0x80031C78u;
constexpr std::uint32_t kCopyLoopEnd = 0x80031C94u;
constexpr std::uint32_t kImageWrapperReturn = 0x8004CA9Cu;
constexpr std::uint32_t kOriV1ZeroUpper = 0x34030000u;

struct LzExtent {
  std::string status;
  std::size_t sourceBytes = 0;
  std::size_t outputBytes = 0;
};

// Count the authenticated LZ stream's output without writing guest memory. A zero control byte
// terminates it; the wrapper's actual guest instruction and remaining mapped RAM bound the scan.
LzExtent scanLzExtent(const std::uint8_t *source, std::size_t sourceLimit, std::size_t outputLimit) {
  std::size_t input = 0;
  std::size_t output = 0;
  while (input < sourceLimit) {
    auto control = source[input++];
    if (control == 0) {
      return {"complete", input, output};
    }
    for (; control > 1; control >>= 1) {
      auto bytes = (control & 1u) != 0 ? 1u : 2u;
      if (bytes > sourceLimit - input) {
        return {"truncated-token", input, output};
      }
      auto length = std::size_t{1};
      if (bytes == 2u) {
        auto token = (static_cast<std::uint32_t>(source[input]) << 8u) | source[input + 1u];
        length = (token >> 11u) & 31u;
        if (length == 0) {
          length = 32u;
        }
      }
      input += bytes;
      if (length > outputLimit - output) {
        return {"exceeds-wrapper-output-limit", input, output};
      }
      output += length;
    }
  }
  return {"missing-terminator-within-mapped-RAM", input, output};
}

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

std::string imageWrapperExtent(Core &core, std::uint32_t source, std::uint32_t outputStart, std::uint32_t outputEnd) {
  // FUN_8004CA40 saves the image table in s3, advances s1 over eight-byte entries, and keeps the
  // destination in s5 while FUN_80031BFC executes. Its call delay slot sets a0=s3+*(s1+4).
  auto tableBase = core.r[19];
  auto entryPointer = core.r[17];
  auto index = core.r[16];
  auto count = core.r[20];
  auto wrapperDestination = core.r[21];
  auto expectedEntryPointer = static_cast<std::uint64_t>(tableBase) + static_cast<std::uint64_t>(index) * 8u;
  auto limitInstruction = core.mem_r32(kImageWrapperReturn);
  if (static_cast<std::int32_t>(count) <= 0 || index >= count || expectedEntryPointer != entryPointer ||
      entryPointer > std::numeric_limits<std::uint32_t>::max() - 4u ||
      !core.mappedMainRamRange(entryPointer + 4u, 4u) || wrapperDestination != outputStart ||
      (limitInstruction & 0xFFFF0000u) != kOriV1ZeroUpper) {
    return lucent::format("wrapper_entry=unresolved table=0x{:08X} entry=0x{:08X} index={}/{} "
                          "wrapper_destination=0x{:08X} limit_instruction=0x{:08X} scan=not-run scanned=0",
                          tableBase,
                          entryPointer,
                          index,
                          count,
                          wrapperDestination,
                          limitInstruction);
  }
  auto outputLimit = static_cast<std::size_t>(limitInstruction & 0xFFFFu);

  auto sourceOffset = core.mem_r32(entryPointer + 4u);
  auto entryAddress = static_cast<std::uint64_t>(tableBase) + sourceOffset;
  if (entryAddress > std::numeric_limits<std::uint32_t>::max()) {
    return lucent::format("wrapper_entry=unresolved offset=0x{:08X} base-plus-offset-overflows "
                          "scan=not-run scanned=0",
                          sourceOffset);
  }
  auto entry = static_cast<std::uint32_t>(entryAddress);
  auto entryRam = mappedByte(core, entry);
  auto cursorRam = mappedByte(core, source);
  auto outputBeginRam = mappedByte(core, outputStart);
  auto outputEndRam = mappedByte(core, outputEnd);
  if (!entryRam || !cursorRam || !outputBeginRam || !outputEndRam || source < entry || *cursorRam < *entryRam ||
      source - entry != *cursorRam - *entryRam || outputEnd < outputStart || *outputEndRam < *outputBeginRam ||
      outputEnd - outputStart != *outputEndRam - *outputBeginRam) {
    return lucent::format("wrapper_entry=unresolved source=0x{:08X} table_source=0x{:08X} "
                          "mapped_monotonic_span=0 scan=not-run scanned=0",
                          source,
                          entry);
  }

  auto extent = scanLzExtent(&core.ram[*entryRam], sizeof(core.ram) - *entryRam, outputLimit);
  auto consumed = *cursorRam - *entryRam;
  auto sourceEnd = *entryRam + extent.sourceBytes;
  auto outputFinalEnd = *outputBeginRam + extent.outputBytes;
  auto overlapsOutput = *entryRam < outputFinalEnd && *outputBeginRam < sourceEnd;
  auto consistent = extent.status == "complete" && consumed <= extent.sourceBytes &&
                    outputEnd - outputStart <= extent.outputBytes && outputFinalEnd <= sizeof(core.ram) &&
                    !overlapsOutput;
  auto expectedOutput = consistent ? lucent::format("{}", extent.outputBytes) : std::string{"unknown"};
  return lucent::format("wrapper_entry=0x{:08X}(RAM+0x{:06X}) table=0x{:08X} entry_index={}/{} "
                        "source_consumed={}/{} parsed_output={} expected_output_from_RAM={}/{} "
                        "scan={} consistent={}",
                        entry,
                        *entryRam,
                        tableBase,
                        index,
                        count,
                        consumed,
                        extent.sourceBytes,
                        extent.outputBytes,
                        expectedOutput,
                        outputLimit,
                        extent.status,
                        consistent ? 1 : 0);
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
    return prefix + " live_lz=unreached-at-exit wrapper_entry=unreached scan=not-run scanned=0; "
                    "nested earlier calls are not observed";
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

  auto wrapperExtent = core.r[31] == kImageWrapperReturn
                           ? imageWrapperExtent(core, source, outputStart, destination)
                           : std::string{"wrapper_entry=unreached scan=not-run scanned=0"};
  return prefix + lucent::format(" live_lz[ra=0x{:08X} a0/source={} a1/destination={} a2/length={} "
                                 "a3/backref={} t1/output_start={}] output_progress={} copy_progress={} {}",
                                 core.r[31],
                                 mappedAddress(core, source),
                                 mappedAddress(core, destination),
                                 length,
                                 mappedAddress(core, backReference),
                                 mappedAddress(core, outputStart),
                                 outputProgress,
                                 copyProgress,
                                 wrapperExtent);
}

} // namespace tekken3
