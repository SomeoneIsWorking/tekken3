#pragma once

#include "game_runtime.h"

#include <cstdint>

namespace tekken3 {

// Physical resident-text extent measured from the selected PS-X EXE. The boundary harness receives
// it from the executable manifest, so the native runtime does not duplicate those measured values.
struct ResidentProgramRange {
  std::uint32_t lo;
  std::uint32_t hi;
};

// Process-lifetime owner of Tekken 3's framework-facing behavior. Immutable executable facts live
// on GuestProgramImage; behavior belongs on this runtime or cohesive owners it creates.
class Tekken3Runtime final : public GameRuntime {
public:
  Tekken3Runtime() = default;
  explicit Tekken3Runtime(ResidentProgramRange residentProgram);

  void *createContext(Core &core) override;
  void destroyContext(void *context) override;
  void registerOverrides(Game &game) override;
  [[noreturn]] void bootInit(Core &core) override;
  const GuestProgramImage *guestProgramImage() const override;

private:
  const GuestProgramImage programImage_{};
};

} // namespace tekken3
