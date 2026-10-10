#include "entry/product_launch.h"

#include "c_subsys.h"
#include "cfg.h"
#include "core.h"
#include "game.h"
#include "gpu_vk.h"
#include "machine.h"
#include "program/title_runtime.h"
#include "psx_exe_image.h"

#include <cstdint>
#include <memory>

namespace {

constexpr const char *kDefaultExecutable = "scratch/bin/tekken3/SLUS_004.02";

// A run with no explicit bound and no window is unattended: bound it, or it never ends.
constexpr std::uint32_t kUnattendedFieldCap = 120;

} // namespace

namespace tekken3 {

int launchProduct(TitleRuntime &runtime, int argc, char **argv) {
  const char *const executable = argc > 1 ? argv[1] : kDefaultExecutable;

  psxport_install_game(runtime);
  auto game = std::make_unique<Game>();
  // No legacy GameConfig here, so bind the disc key on the disc subsystem directly.
  game->disc.env_key = "PSXPORT_TEKKEN3_DISC";
  Core *const core = &game->core;

  watchdog_init();
  load_exe(executable, core);

  psx::Machine machine{*game};
  machine.bindDevices();
  machine.prepare();
  runtime.bootInit(*core);

  // The control channel attaches before the cap is settled: an attached client means a driven run.
  const int requestedFrames = cfg_int("PSXPORT_NATIVE_FRAMES", 0);
  std::uint32_t frameLimit = requestedFrames > 0 ? static_cast<std::uint32_t>(requestedFrames) : 0u;
  if (frameLimit == 0 && !gpu_vk_windowed()) {
    frameLimit = kUnattendedFieldCap;
  }
  machine.attachControlChannel(frameLimit);
  machine.run(frameLimit);
  return 0;
}

} // namespace tekken3
