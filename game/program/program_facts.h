#pragma once

#include <cstdint>

namespace tekken3::program {

// SLUS_004.02 image mapping.
inline constexpr std::uint32_t kEntry = 0x80079C70u;
inline constexpr std::uint32_t kResidentPhysicalLo = 0x00010000u;
inline constexpr std::uint32_t kResidentPhysicalHi = 0x00131000u;

} // namespace tekken3::program
