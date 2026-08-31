#include "core.h"
#include "game.h"
#include "platform_hle.h"
#include "tekken3_runtime.h"

#include <cstdint>
#include <cstdio>
#include <memory>
#include <stdexcept>

namespace {

constexpr tekken3::ResidentProgramRange kFixtureRange{0x00001000u, 0x00002000u};

} // namespace

int main() {
  static tekken3::Tekken3Runtime interpreterOnlyRuntime;
  psxport_install_game(interpreterOnlyRuntime);
  {
    auto interpreterCore = std::make_unique<Core>();
    if (interpreterCore->guestProgramImage != nullptr) {
      std::fprintf(stderr, "runtime_seam: FAIL — interpreter-only runtime invented resident program facts\n");
      return 1;
    }
  }

  bool invalidRangeRefused = false;
  try {
    tekken3::Tekken3Runtime invalid{{0x00010000u, 0x00010000u}};
  } catch (const std::invalid_argument &) {
    invalidRangeRefused = true;
  }
  if (!invalidRangeRefused) {
    std::fprintf(stderr, "runtime_seam: FAIL — an empty resident program range was accepted\n");
    return 1;
  }

  static tekken3::Tekken3Runtime runtime{kFixtureRange};
  psxport_install_game(runtime);

  const RenderCapabilities capabilities = runtime.renderCapabilities();
  if (capabilities.defaultPath != RenderPath::Gte || capabilities.nativeRenderPath ||
      capabilities.temporalInterpolation) {
    std::fprintf(stderr, "runtime_seam: FAIL — Tekken did not declare the widescreen-only profile\n");
    return 1;
  }
  if (!capabilities.supports(RenderPath::Gte) || !capabilities.supports(RenderPath::Psx) ||
      capabilities.supports(RenderPath::Native)) {
    std::fprintf(stderr, "runtime_seam: FAIL — Tekken render-path support does not match its scope\n");
    return 1;
  }
  if (!capabilities.playerSelectable(RenderPath::Gte) || capabilities.playerSelectable(RenderPath::Psx) ||
      capabilities.playerSelectable(RenderPath::Native) || capabilities.playerPathCount() != 1) {
    std::fprintf(stderr, "runtime_seam: FAIL — Tekken exposed a diagnostic or native player path\n");
    return 1;
  }
  if (render_path_resolve(RenderPath::Native, capabilities) != RenderPath::Gte ||
      render_path_next_supported(RenderPath::Gte, capabilities, RenderPathAudience::Player) != RenderPath::Gte ||
      render_path_next_supported(RenderPath::Gte, capabilities, RenderPathAudience::Diagnostic) != RenderPath::Psx) {
    std::fprintf(stderr, "runtime_seam: FAIL — shared path resolution ignored Tekken capabilities\n");
    return 1;
  }

  const PlatformHlePlan *const hle = runtime.platformHlePlan();
  if (!hle || hle->vsyncAddress != 0x800859A8u || hle->bindingCount != 0 || hle->windowLo[0] != 0x800859A8u ||
      hle->windowHi[0] != 0x80085B20u) {
    std::fprintf(stderr,
                 "runtime_seam: FAIL — Tekken did not declare protected VSync ownership at the "
                 "measured address\n");
    return 1;
  }

  const GuestPadBufferLayout *const pad = runtime.guestPadBufferLayout();
  if (!pad || pad->slot0Buffer != 0x800A9132u || pad->slot1Buffer != 0x800A915Cu || pad->slotPointerTable != 0 ||
      pad->slotPointerStride != 4) {
    std::fprintf(stderr,
                 "runtime_seam: FAIL — Tekken did not declare the two measured Sony libpad "
                 "receive buffers\n");
    return 1;
  }
  if (!runtime.guestWidescreenProjection()) {
    std::fprintf(stderr, "runtime_seam: FAIL — Tekken did not publish its measured guest projection owner\n");
    return 1;
  }

  const auto policyGame = std::make_unique<Game>();
  if (game_guest_vram_is_picture(*policyGame)) {
    std::fprintf(stderr, "runtime_seam: FAIL — boundary-only Tekken runtime treated guest VRAM as a picture\n");
    return 1;
  }

  // Core owns the complete 2 MiB guest RAM plus device state and is intentionally heap-resident in
  // every production Game. Keep this seam check on the same lifetime path.
  auto core = std::make_unique<Core>();
  if (core->runtime != &runtime) {
    std::fprintf(stderr, "runtime_seam: FAIL — Core did not snapshot the derived Tekken runtime\n");
    return 1;
  }
  if (!core->guestProgramImage || core->guestProgramImage->residentText.begin != kFixtureRange.lo ||
      core->guestProgramImage->residentText.end != kFixtureRange.hi) {
    std::fprintf(stderr, "runtime_seam: FAIL — resident program facts did not reach GuestProgramImage\n");
    return 1;
  }
  if (core->cfg != nullptr || core->hooks != nullptr || core->gameCtx != nullptr) {
    std::fprintf(stderr, "runtime_seam: FAIL — direct runtime exposed legacy config, hooks, or context\n");
    return 1;
  }

  std::printf("runtime_seam: PASS — Core owns the direct runtime, 2/2 resident-range facts reach "
              "GuestProgramImage, 3/3 legacy views are null, 1/1 invalid range is refused, "
              "13/13 render-capability facts enforce guest rendering without temporal interpolation, "
              "5/5 platform-HLE facts declare protected VSync ownership, 4/4 pad-layout facts reach "
              "the shared host service, the guest projection owner is present, and guest VRAM picture "
              "ownership is false\n");
  std::printf("runtime_seam: NOT covered — generated execution, devices, frames, or gameplay\n");
  return 0;
}
