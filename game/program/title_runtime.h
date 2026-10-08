#pragma once

#include "game_runtime.h"
#include "program/platform_hle_plan.h"
#include "widescreen/widescreen.h"

#include <cstdint>

namespace tekken3 {

// Physical resident-text extent of the selected PS-X EXE.
struct ResidentProgramRange {
  std::uint32_t lo;
  std::uint32_t hi;
};

// Tekken 3's framework-facing runtime.
class TitleRuntime final : public GameRuntime {
public:
  explicit TitleRuntime(ResidentProgramRange residentProgram);
  TitleRuntime(ResidentProgramRange residentProgram, std::uint32_t programEntry);

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
  widescreen::WidescreenProjection projection_;
};

} // namespace tekken3
