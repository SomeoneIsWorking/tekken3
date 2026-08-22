#pragma once

#include "game_iface.h"

#include <cstdint>

namespace tekken3 {

// Physical resident-text extent measured from the selected PS-X EXE. The boundary harness receives
// it from the executable manifest, so the native runtime does not duplicate those measured values.
struct ResidentProgramRange {
  std::uint32_t lo;
  std::uint32_t hi;
};

// Process-lifetime owner of Tekken 3's framework-facing behavior. The legacy base is bounded debt:
// psxport's generated-code router still reads recMainLo/recMainHi through Core::cfg. No behavior is
// delegated through GameHooks, and new Tekken behavior belongs on this runtime or cohesive owners it
// creates.
class Tekken3Runtime final : public LegacyGameRuntimeAdapter {
public:
  Tekken3Runtime();
  explicit Tekken3Runtime(ResidentProgramRange residentProgram);

  void registerOverrides(Game &game) override;
  [[noreturn]] void bootInit(Core &core) override;
};

} // namespace tekken3
