// widescreen.h — this title's widescreen projection policy: the widened view the guest renders, and
// the two horizontal clippers that keep the margins showing what the wider view admits.
#pragma once

#include "guest_widescreen_projection.h"
#include "widescreen/stage_tile_wedge.h"

#include <cstdint>

class Core;

namespace tekken3::widescreen {

// The runtime's own projection policy, reached from Core by the overrides below. An override that
// cannot find it refuses rather than running against another title's plan.
const WidescreenProjection &policyFrom(Core *core, const char *owner);

class WidescreenProjection final : public GuestWidescreenProjection {
public:
  using GuestBody = void (*)(Core *);
  using ProjectionLatch = GuestProjectionPlan (*)(Core *, GuestProjectionGeometry);

  WidescreenProjection();
  explicit WidescreenProjection(ProjectionLatch latch);
  WidescreenProjection(ProjectionLatch latch, GuestBody retailDimensions);

  PresentationAspect presentationAspect(const Core &core) const override;
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
