// loader_lifecycle.h — the recovered CD-read lifecycle that holds the NAMCO PRESENTS card.
//
// WHY THIS FILE EXISTS. The product's NAMCO PRESENTS card never leaves, and the CD completion is
// the cause; a parked note once refuted that on the strength of a reader count that had itself
// missed the addresses, and this file is the recovered behaviour that settles it.
//
// Every address, field offset and branch target below is decoded from the authenticated executable
// with `psxport/tools/disasm.py`. Nothing here is quoted from a comment, because two records in
// this repository's own history were wrong precisely because they were quoted from one.
//
// WHAT THIS IS, AND WHAT IT IS NOT. This is a READING of guest behaviour, kept as named structures
// and constants so the next reader does not have to re-derive it, plus the exact place the port has
// to intervene. It is NOT a decompilation that is shipped as guest behaviour and it is NOT a
// translation of guest code into host objects: the guest's own bodies keep running on the JIT, and
// the only thing this repository ships is a native override that delivers the callback the guest
// already registered. The decomp filter that put this file here is: it sits on the path of not
// reaching a fight, and it has no native owner yet.

#ifndef TEKKEN3_LOADER_LIFECYCLE_H
#define TEKKEN3_LOADER_LIFECYCLE_H

#include <cstdint>

namespace tekken3::loader {

// ---------------------------------------------------------------------------
// The loader's state block, which lives at 0x800A0698 and is addressed as a base
// register plus a byte displacement throughout the loader. Decoded:
//   0x8006BEB4  addiu $s0,$v0,0x698   over `lui $v0,0x800A`  ->  $s0 = 0x800A0698
// Every access below is `N($s0)`, so the block is a struct, not a set of unrelated globals.
// ---------------------------------------------------------------------------
inline constexpr std::uint32_t kLoaderBase = 0x800A0698u;

struct LoaderState {
  std::uint8_t &busy;   // +6 = 0x800A069E. Set by the read request, cleared on completion.
  std::uint8_t &held;   // +7 = 0x800A069F. "a read is in flight"; the wait byte.
  std::uint16_t &phase; // +4 = 0x800A069C
  std::uint32_t &link;  // +0 = 0x800A0698, the next record in the loader's chain
};

// ---------------------------------------------------------------------------
// FUN_8006BEA8 — the wait the card is sitting in. Decoded in full:
//
//   0x8006BEBC  lbu   $v0,7($s0)          ; read 0x800A069F
//   0x8006BEC4  beqz  $v0,0x8006BEF8      ; not in flight -> straight to the clear
//   0x8006BECC  jal   0x8006C1FC          ; issue ONE more sector request
//   0x8006BED4  lbu   $v0,6($s0)          ; read 0x800A069E
//   0x8006BEDC  beqz  $v0,0x8006BEF4
//   0x8006BEE4  lbu   $v0,6($v1)   <-- the spin: an UNTINED loop on 0x800A069E
//   0x8006BEEC  bnez  $v0,0x8006BEE4
//   0x8006BEFC  sb    $zero,7($v0)        ; clear 0x800A069F
//
// THE SPIN IS THE POINT, and it is why the port could not simply "finish the read". This loop has
// no timeout and no counter: it exits only when 0x800A069E goes to zero, which happens only in the
// sector callback. It is also an infinite loop from the executor's point of view, which is why the
// mode call must be entered through the suspending entry rather than a per-field one.
// ---------------------------------------------------------------------------
inline constexpr std::uint32_t kWaitForRead = 0x8006BEA8u;
inline constexpr std::uint32_t kWaitInnerSpin = 0x8006BEE4u; // bnez back-edge, 0x800A069E
inline constexpr std::uint32_t kWaitClearsHeld = 0x8006BEFCu;

// ---------------------------------------------------------------------------
// FUN_8006C1FC — issue one sector. It calls the byte reader at 0x8006C23C and, when a read is
// already in flight, sets 0x800A069E and returns 1; otherwise it returns 0.
// ---------------------------------------------------------------------------
inline constexpr std::uint32_t kIssueOneSector = 0x8006C1FCu;

// ---------------------------------------------------------------------------
// FUN_8006C084 region, at 0x8006C1A4 — where a read is STARTED. Decoded:
//   0x8006C1A4  sb     $v0,7($s1)     ; 0x800A069F = 1  <- the card's wait byte goes up
//   0x8006C1B0  addiu  $a0,$zero,0xA0
//   0x8006C1BC  jal    0x8008F08C     ; submit to the CD chain
//   0x8006C1C0  addiu  $a3,$s3,-15764 ; $a3 = 0x8006C26C  <- the completion callback
// So the byte the card waits on and the callback that would clear it are set in ONE breath, by the
// guest, with the guest's own `jal`. Nothing is missing from the guest; the port was not calling it.
// ---------------------------------------------------------------------------
inline constexpr std::uint32_t kStartReadSetsHeld = 0x8006C1A4u;
inline constexpr std::uint32_t kChainSubmit = 0x8008F08Cu;
inline constexpr std::uint32_t kChainCompletionCallback = 0x8006C26Cu;

// The record the chain stores the callback in. `0x8008F184  sw s3,12(v0)` puts $a3 at +12, and the
// value was measured at exactly one address in a 524,288-word RAM capture.
inline constexpr std::uint32_t kChainRecordSlot = 0x800A3DD0u;
inline constexpr std::uint32_t kChainCallbackOffset = 12u;

// ---------------------------------------------------------------------------
// FUN_8006C26C — the chain's completion callback. Decoded in full:
//   0x8006C270  andi  $a0,$a0,0xFF
//   0x8006C274  addiu $v0,$zero,2
//   0x8006C278  bne   $a0,$v0,0x8006C290   ; only class 2 does anything
//   0x8006C280  lui   $a0,0x8007
//   0x8006C284  addiu $a0,$a0,-0x3D60       ; $a0 = 0x8007C2A0  <- the SECTOR callback
//   0x8006C288  jal   0x80091F38            ; install it
//   0x8006C28C  addiu $a1,$zero,-1
//
// THIS IS THE HOP issue 0018 called hop 1, and it is the one the port was not making. It is a
// class-2 completion that installs the per-sector callback; nothing about it is a clock question.
// ---------------------------------------------------------------------------
inline constexpr std::uint32_t kChainCompletionClass = 2u;
inline constexpr std::uint32_t kSectorCallbackEntry = 0x8007C2A0u;
inline constexpr std::uint32_t kInstallSectorCallback = 0x80091F38u;

// ---------------------------------------------------------------------------
// FUN_80091F38 — installs the sector callback. Decoded in full, with $s0 = 0x8009B8E8:
//   0x80091F50  lw    $v0,($s0)              ; 0x8009B8E8, the registration flag
//   0x80091F58  beq   $v0,$s1,0x80091FA4     ; already installed -> return 0
//   0x80091F5C  move  $v1,$a0               ; the callback
//   0x80091F6C  sw    $v0,-0x20($s0)        ; 0x8009B8C8 = -1
//   0x80091F70  sw    $zero,-0x1c($s0)      ; 0x8009B8CC = 0
//   0x80091F74  sw    $zero,-0x14($s0)      ; 0x8009B8D4 = 0
//   0x80091F78  sw    $v1,-0x18($s0)        ; 0x8009B8D0 = the sector callback   <-- THE SLOT
//   0x80091F80  sw    $a1,-0x10($s0)        ; 0x8009B8D8 = the second argument
//   0x80091FA0  sw    $s1,($s0)             ; 0x8009B8E8 = 1
//
// So the block at 0x8009B8C8 is a RECORD, and 0x8009B8D0 is the callback field of it.
// ---------------------------------------------------------------------------
inline constexpr std::uint32_t kSectorCallbackRecord = 0x8009B8C8u;
inline constexpr std::uint32_t kSectorCallbackSlot = 0x8009B8D0u;     // +8 into the record
inline constexpr std::uint32_t kSectorCallbackArgument = 0x8009B8D8u; // +16
inline constexpr std::uint32_t kSectorCallbackFlag = 0x8009B8E8u;
inline constexpr std::uint32_t kSectorCallbackState = 0x8009B8C8u;

// ---------------------------------------------------------------------------
// The DISPATCH of the sector callback.
//
// An earlier note recorded that "no instruction in the authenticated text reads 0x8009B8D0", and
// concluded the sector callback was installed into a slot nothing dispatches. **Both the claim and
// the conclusion are wrong**, and the decoder check is one instruction apart:
//
//   0x80092048  lui   $s1,0x800A
//   0x8009204C  addiu $s1,$s1,0xB8C8    ;  $s1 = 0x8009B8C8   <- the record base
//   0x80092110  lw    $a3,8($s1)         ;  $a3 = *(0x8009B8D0)  THE SLOT
//   0x80092118  beqz  $a3,0x80092150     ;  no callback -> skip
//   0x8009213C  jalr  $a3                ;  CALL THE SECTOR CALLBACK
//
// The register is `$a3` (r7), not `$v1`: `0x80092110` is `0x8E270008`, and its rt field is 7.
// A constant-propagation walk of the authenticated text finds **6 readers of 0x8009B8D0 in 295,936
// walked words**, against the 0 the parked note reported. The `jalr $a3` is the whole hop 2.
// ---------------------------------------------------------------------------
inline constexpr std::uint32_t kDispatchSectorCallback = 0x8009213Cu;
inline constexpr std::uint32_t kDispatchLoadsSlot = 0x80092110u;
inline constexpr std::uint32_t kDispatchPerSectorHandler = 0x80092034u;

// ---------------------------------------------------------------------------
// FUN_8006C2A0 — the sector callback itself, class 1. Decoded in full:
//   0x8006C2C0  bne   $a0,$s4,0x8006C41C   ; $s4 = 1: only class 1
//   0x8006C2CC  addiu $s2,$s3,0x698        ; $s2 = 0x800A0698
//   0x8006C2D0  lbu   $v0,6($s2)           ; 0x800A069E, the busy byte
//   0x8006C2D8  beqz  $v0,0x8006C308
//   0x8006C2E0  jal   0x80091FBC           ; consume the sector
//   0x8006C2EC  sb    $zero,7($s2)         ; *** CLEARS 0x800A069F ***
//   0x8006C2F0  sh    $s4,0x5D8($v0)       ; 0x800AE5D8 = 1
//
// 0x8006C2EC is the only writer that clears 0x800A069F on this path, and it is INSIDE this
// callback. That is the whole causal chain in one line: the card waits on 0x800A069F, and the only
// thing in the image that clears it runs inside a callback the guest registers and nothing calls.
// ---------------------------------------------------------------------------
inline constexpr std::uint32_t kSectorCallbackBody = 0x8006C2A0u;
inline constexpr std::uint32_t kSectorCallbackClearsHeld = 0x8006C2ECu;
inline constexpr std::uint32_t kConsumeSector = 0x80091FBCu;
inline constexpr std::uint32_t kSectorEventClass = 1u;

} // namespace tekken3::loader

#endif // TEKKEN3_LOADER_LIFECYCLE_H
