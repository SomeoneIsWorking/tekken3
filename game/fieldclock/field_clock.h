// The guest VBlank field word Tekken's linked libetc VSync returns.
#pragma once

#include <cstdint>

class Core;

namespace tekken3::field {

// Linked libetc VSync entry and the half-open end of its body (next function at 0x80085B20).
inline constexpr std::uint32_t kEntry = 0x800859A8u;
inline constexpr std::uint32_t kBodyEnd = 0x80085B20u;

// Field count a negative VSync mode returns; FUN_80086358 zeroes it, FUN_800863B0 increments it.
inline constexpr std::uint32_t kCounter = 0x8009AC68u;

std::uint32_t readCounter(Core &core);

} // namespace tekken3::field
