#pragma once

#include "game_runtime.h"
#include "sync_native.h"
#include "widescreen.h"

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
  explicit Tekken3Runtime(ResidentProgramRange residentProgram);
  Tekken3Runtime(ResidentProgramRange residentProgram, std::uint32_t programEntry);

  RenderCapabilities renderCapabilities() const override;
  bool guestVramIsPicture(const Game &game) const override;
  const PlatformHlePlan *platformHlePlan() const override;
  const GuestPadBufferLayout *guestPadBufferLayout() const override;
  const GuestWidescreenProjection *guestWidescreenProjection() const override;
  void *createContext(Core &core) override;
  void destroyContext(void *context) override;
  void registerOverrides(Game &game) override;
  void bootInit(Core &core) override;
  std::unique_ptr<FrameDriver> createFrameDriver(Game &game) override;
  const GuestProgramImage *guestProgramImage() const override;

private:
  const GuestProgramImage programImage_{};
  const std::uint32_t programEntry_ = 0;
  Tekken3Widescreen widescreen_;
};

} // namespace tekken3
