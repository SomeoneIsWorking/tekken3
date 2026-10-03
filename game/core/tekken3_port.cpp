#include "tekken3_port.h"
#include "psx_exe_image.h"

#include "c_subsys.h"
#include "cfg.h"
#include "core.h"
#include "game.h"
#include "gpu_vk.h" // gpu_vk_windowed — the windowed/headless discriminator
#include "machine.h"
#include "render_mode.h"
#include "tekken3_runtime.h"

#include <memory>

extern "C" {
void watchdog_init(void);
}

namespace {

constexpr const char *kDefaultExecutable = "scratch/bin/tekken3/SLUS_004.02";

} // namespace

namespace tekken3 {

int runPort(Tekken3Runtime &runtime, int argc, char **argv) {
  const char *const executable = argc > 1 ? argv[1] : kDefaultExecutable;

  psxport_install_game(runtime);
  auto game = std::make_unique<Game>();
  // Direct runtimes deliberately have no legacy GameConfig, so bind the title's disc key at the
  // disc subsystem itself. This keeps env/.env/drop-in resolution available without reviving the
  // legacy config adapter.
  game->disc.env_key = "PSXPORT_TEKKEN3_DISC";
  Core *const core = &game->core;

  watchdog_init();
  load_exe(executable, core);

  // The composition every product shares: the per-Core device binds in the framework's measured
  // order, the `a0`/`a1` the BIOS leaves, this title's overrides, and the frame-loop preflight that
  // refuses a product with no finite frame owner.
  psx::Machine machine{*game};
  machine.bindDevices();
  render_path_install(core);
  machine.prepare();
  runtime.bootInit(*core);

  // This title's own frame bound. The endpoint is attached BEFORE the cap is settled, because an
  // attached client means the run is driven rather than unattended, and a cap ends the process
  // before anyone can drive it.
  const int requestedFrames = cfg_int("PSXPORT_NATIVE_FRAMES", 0);
  std::uint32_t frameLimit = requestedFrames > 0 ? static_cast<std::uint32_t>(requestedFrames) : 0u;
  if (frameLimit == 0 && !gpu_vk_windowed()) {
    frameLimit = 120;
  }
  machine.attachControlChannel(frameLimit);
  machine.run(frameLimit);
  return 0;
}

} // namespace tekken3
