#pragma once

#include <cstdint>

struct Core;

namespace tekken3 {

using RecompiledFunction = void (*)(Core *);
using RecompiledOverrideSetter = void (*)(std::uint32_t, RecompiledFunction);

// Product-only generated bodies supplied by recomp_register.cpp. Keeping these pointers in a typed
// bundle lets the title runtime retain each generated super without making hermetic runtime tests
// link the gitignored generated program.
struct RecompiledProgramBindings {
  RecompiledFunction mainSuper = nullptr;
  RecompiledFunction frameBarrierSuper = nullptr;
  RecompiledFunction displayInitSuper = nullptr;
  RecompiledFunction cdSyncSuper = nullptr;
  RecompiledFunction cdReadySuper = nullptr;
  RecompiledFunction cdControlSuper = nullptr;
  RecompiledFunction cdCommandSuper = nullptr;
  RecompiledFunction cdQueueStartSuper = nullptr;
  RecompiledFunction cdQueueResultSuper = nullptr;
  RecompiledFunction gpuTimeoutArmSuper = nullptr;
  RecompiledFunction gpuTimeoutPollSuper = nullptr;
  RecompiledFunction viewDimensionsSuper = nullptr;
  RecompiledFunction stageClipSuper = nullptr;
  RecompiledFunction effectClipSuper = nullptr;
  RecompiledOverrideSetter setOverride = nullptr;

  [[nodiscard]] bool complete() const {
    return mainSuper && frameBarrierSuper && displayInitSuper && cdSyncSuper && cdReadySuper && cdControlSuper &&
           cdCommandSuper && cdQueueStartSuper && cdQueueResultSuper && gpuTimeoutArmSuper && gpuTimeoutPollSuper &&
           viewDimensionsSuper && stageClipSuper && effectClipSuper && setOverride;
  }
};

} // namespace tekken3
