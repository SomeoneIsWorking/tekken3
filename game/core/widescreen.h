#pragma once

#include "guest_widescreen_projection.h"

#include <cstdint>

class Core;

namespace tekken3 {

struct RecompiledProgramBindings;

class Tekken3Widescreen final : public GuestWidescreenProjection {
public:
  using GuestBody = void (*)(Core *);
  using ProjectionLatch = GuestProjectionPlan (*)(Core *, GuestProjectionGeometry);

  Tekken3Widescreen();
  explicit Tekken3Widescreen(ProjectionLatch latch);
  Tekken3Widescreen(ProjectionLatch latch, GuestBody retailDimensions);

  PresentationAspect presentationAspect(const Core &core) const override;
  void install(const RecompiledProgramBindings &bindings);
  void publishDimensions(Core &core) const;
  void clipStagePrimitives(Core &core) const;
  void clipEffectPrimitive(Core &core) const;

  static GuestProjectionGeometry measuredGeometry(std::uint32_t viewWidth, std::uint32_t viewHeight);

private:
  static void publishDimensionsOverride(Core *core);
  static void stageClipOverride(Core *core);
  static void effectClipOverride(Core *core);

  ProjectionLatch latch_;
  GuestBody retailDimensions_ = nullptr;
  GuestBody retailStageClip_ = nullptr;
  GuestBody retailEffectClip_ = nullptr;
  mutable GuestProjectionPlan plan_;
};

} // namespace tekken3
