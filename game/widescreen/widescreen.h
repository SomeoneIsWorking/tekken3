// Widescreen projection policy: the widened view plus the two horizontal clippers.
#pragma once

#include "guest_widescreen_projection.h"
#include "widescreen/stage_tile_wedge.h"

#include <cstdint>

class Core;

namespace tekken3::widescreen {

// The runtime's projection policy; aborts if Core has none.
const WidescreenProjection &policyFrom(Core *core, const char *owner);

class WidescreenProjection final : public GuestWidescreenProjection {
public:
  using GuestBody = void (*)(Core *);
  using ProjectionLatch = GuestProjectionPlan (*)(Core *, GuestProjectionGeometry);

  WidescreenProjection();
  explicit WidescreenProjection(ProjectionLatch latch);
  WidescreenProjection(ProjectionLatch latch, GuestBody retailDimensions);

  void install(Core &core);
  void publishDimensions(Core &core) const;
  void clipStagePrimitives(Core &core) const;
  void clipEffectPrimitive(Core &core) const;

  [[nodiscard]] const StageTileWedge &stageWedge() const;

  static GuestProjectionGeometry measuredGeometry(std::uint32_t viewWidth, std::uint32_t viewHeight);

private:
  static void publishDimensionsOverride(Core *core);
  static void stageClipOverride(Core *core);
  static void effectClipOverride(Core *core);

  ProjectionLatch latch_;
  GuestBody retailDimensions_ = nullptr;
  GuestBody retailStageClip_ = nullptr;
  GuestBody retailEffectClip_ = nullptr;
  StageTileWedge stageWedge_;
  mutable GuestProjectionPlan plan_;
};

} // namespace tekken3::widescreen
