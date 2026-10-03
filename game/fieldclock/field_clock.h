// field_clock.h — the guest VBlank field word Tekken's linked libetc VSync returns.
//
// One fact, one home. Both consumers of that VSync read this counter: the framework answers a
// negative query only from PlatformHlePlan::vsyncQueryCounterAddress, and the title's own GPU queue
// timeout owner reads the same word because that is what the retail code put in v0.
#pragma once

#include <cstdint>

class Core;

namespace tekken3::field {

// The linked libetc VSync entry and the half-open end of its body, measured from adjacent function
// starts in the executable (previous entry 0x800858B8, next entry 0x80085B20).
inline constexpr std::uint32_t kEntry = 0x800859A8u;
inline constexpr std::uint32_t kBodyEnd = 0x80085B20u;

// The guest VBlank field count a negative VSync mode returns. Read, never written: the value the
// retail leaf produced, not a number the port supplies. FUN_80086358 zeroes it and FUN_800863B0
// increments it per vblank; it is the only such word in the text.
inline constexpr std::uint32_t kCounter = 0x8009AC68u;

// The production binding of that measured word to guest RAM, and the ONLY place the address becomes
// a memory access.
std::uint32_t readCounter(Core &core);

} // namespace tekken3::field
