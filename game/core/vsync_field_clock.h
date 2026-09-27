// vsync_field_clock.h — Tekken 3's measured linked-libetc VSync leaf and the field clock it returns.
//
// One fact, one home. The counter word below is used by BOTH consumers of Tekken's VSync, and
// spelling it twice is how they would drift: the framework answers a negative query only from
// PlatformHlePlan::vsyncQueryCounterAddress, and the title's own GPU-queue timeout owner reads the
// same word because that is what the retail code put in v0.
//
// PROVENANCE. Ghidra over the authenticated SLUS_004.02 at load 0x80010000, and every address below
// is computed from the instruction words rather than transcribed from a decompiler's naming:
//
//   FUN_800859A8 is the linked libetc VSync. Its negative-mode arm is five instructions:
//
//     0x80085A00  bgez  a0, 0x80085A18    ; a0 >= 0 takes the waiting modes
//     0x80085A04  andi  s1, v0, 0xFFFF    ; delay slot: the waiting modes return the count
//     0x80085A08  lui   v0, 0x800A
//     0x80085A0C  lw    v0, -0x5398(v0)   ; v0 = *(0x800A0000 - 0x5398) = *(0x8009AC68)
//     0x80085A10  j     0x80085B0C        ; straight to the epilogue, returning v0
//
//   so a NEGATIVE mode never waits and returns exactly one word, 0x8009AC68.
//
// WHAT THAT WORD IS. The guest's own VBlank field count, and nothing else. FUN_80086358 (the library
// init, whose only caller is FUN_80085D5C at 0x80085DF0) zeroes it and installs FUN_800863B0 as the
// per-vblank callback through FUN_80085BF8; FUN_800863B0 increments that word and then dispatches its
// eight registered callbacks. A constant-propagation sweep of the authenticated text finds exactly
// two stores to it — 0x8008637C and 0x800863DC, the init and the callback — and Ghidra's reference
// model reports ZERO references to it, so the sweep is the authority for the writer census and
// Ghidra is the authority for the read path. tools/verify_vsync_field_clock.py re-derives all of it
// from the image and diffs the constants in this file against the result.
//
// WHY THE TITLE CARES. Tekken calls this leaf 22 times: 21 sites pass a0 = -1 and read the field count
// as a timeout clock, and exactly one — FUN_800B0954's leading VSync(0) — waits for a field. That one
// wait is already owned natively (FrameLoop::runDisplayInit reproduces FUN_800B0954 without it), so the
// only thing the framework needs from the leaf is an answer to the 21 queries, and the only honest
// answer is the word this file names.
#pragma once

#include <cstdint>

class Core;

namespace tekken3::vsync {

// The linked libetc VSync entry and the half-open end of its body, measured from adjacent function
// starts in the executable (previous entry 0x800858B8, next entry 0x80085B20).
inline constexpr std::uint32_t kEntry = 0x800859A8u;
inline constexpr std::uint32_t kBodyEnd = 0x80085B20u;

// The guest VBlank field count that a negative VSync mode returns. Read, never written: this is the
// value the retail leaf produced, not a number the port supplies.
inline constexpr std::uint32_t kFieldCounter = 0x8009AC68u;

// The production binding of the measured word to guest RAM. This is the ONLY place the address
// becomes a memory access, so a test can prove which word the title reads by planting a decoy next
// to it and asking for a different answer.
std::uint32_t readFieldCounter(Core &core);

} // namespace tekken3::vsync
