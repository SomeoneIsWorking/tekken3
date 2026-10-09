// Guest CD-read lifecycle behind the NAMCO PRESENTS card.

#ifndef TEKKEN3_LOADER_LIFECYCLE_H
#define TEKKEN3_LOADER_LIFECYCLE_H

#include <cstdint>

namespace tekken3::loader {

// Loader state block: +4 phase (0x800A069C), +6 busy (0x800A069E), +7 held (0x800A069F, the wait byte).
inline constexpr std::uint32_t kLoaderBase = 0x800A0698u;

// FUN_8006BEA8: the wait. The inner spin on 0x800A069E has no timeout; only the sector callback clears it.
inline constexpr std::uint32_t kWaitForRead = 0x8006BEA8u;
inline constexpr std::uint32_t kWaitInnerSpin = 0x8006BEE4u; // bnez back-edge, 0x800A069E
inline constexpr std::uint32_t kWaitClearsHeld = 0x8006BEFCu;

// FUN_8006C1FC: issues one sector request; returns 1 when a read is already in flight.
inline constexpr std::uint32_t kIssueOneSector = 0x8006C1FCu;

// 0x8006C1A4 sets the held byte, then submits to the CD chain with the completion callback in $a3.
inline constexpr std::uint32_t kStartReadSetsHeld = 0x8006C1A4u;
inline constexpr std::uint32_t kChainSubmit = 0x8008F08Cu;
inline constexpr std::uint32_t kChainCompletionCallback = 0x8006C26Cu;

// The chain stores the callback at +12 of this record (0x8008F184).
inline constexpr std::uint32_t kChainRecordSlot = 0x800A3DD0u;
inline constexpr std::uint32_t kChainCallbackOffset = 12u;

// FUN_8006C26C: a class-2 completion installs the per-sector callback via FUN_80091F38.
inline constexpr std::uint32_t kChainCompletionClass = 2u;
inline constexpr std::uint32_t kSectorCallbackEntry = 0x8006C2A0u;
inline constexpr std::uint32_t kInstallSectorCallback = 0x80091F38u;

// FUN_80091F38 fills this record; the callback field is +8.
inline constexpr std::uint32_t kSectorCallbackRecord = 0x8009B8C8u;
inline constexpr std::uint32_t kSectorCallbackSlot = 0x8009B8D0u;
inline constexpr std::uint32_t kSectorCallbackArgument = 0x8009B8D8u;
inline constexpr std::uint32_t kSectorCallbackFlag = 0x8009B8E8u;

// Dispatch: 0x80092110 loads the slot into $a3, 0x8009213C is the jalr.
inline constexpr std::uint32_t kDispatchSectorCallback = 0x8009213Cu;
inline constexpr std::uint32_t kDispatchLoadsSlot = 0x80092110u;
inline constexpr std::uint32_t kDispatchPerSectorHandler = 0x80092034u;

// FUN_8008F850: the libcd ready hook the ISR calls for each data-ready INT; it forwards to the per-sector handler.
inline constexpr std::uint32_t kReadyHook = 0x8008F850u;
inline constexpr std::uint32_t kReadyHookTail = 0x8008F8F4u;
// FUN_800842E0 discards pending controller INT flags; FUN_80084A30 is the ISR that would have serviced them.
inline constexpr std::uint32_t kFlushInterrupts = 0x800842E0u;
inline constexpr std::uint32_t kCdIsr = 0x80084A30u;
inline constexpr std::uint32_t kHeldByte = 0x800A069Fu;

// FUN_8006C2A0: the class-1 sector callback; 0x8006C2EC is the only clear of 0x800A069F on this path.
inline constexpr std::uint32_t kSectorCallbackBody = 0x8006C2A0u;
inline constexpr std::uint32_t kSectorCallbackClearsHeld = 0x8006C2ECu;
inline constexpr std::uint32_t kConsumeSector = 0x80091FBCu;
inline constexpr std::uint32_t kSectorEventClass = 1u;

} // namespace tekken3::loader

#endif // TEKKEN3_LOADER_LIFECYCLE_H
