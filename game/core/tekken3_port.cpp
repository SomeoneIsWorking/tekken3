#include "tekken3_port.h"
#include "hw_bind.h"
#include "psx_exe_image.h"

#include "c_subsys.h"
#include "cfg.h"
#include "core.h"
#include "frame_loop_shell.h"
#include "game.h"
#include "render_mode.h"
#include "tekken3_runtime.h"

#include <lucent/log.h>

#include <memory>

extern "C" {
void mdec_init(void);
void spu_init(void);
void watchdog_init(void);
}

void gte_bind(Core *core);
void mdec_bind(Core *core);
void spu_bind(Core *core);
void xa_bind(Core *core);

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

  gte_init();
  gte_bind(core);
  core->rsub.projprim.bind(core);
  mdec_init();
  mdec_bind(core);
  spu_init();
  spu_bind(core);
  xa_bind(core);
  game->spu_audio.init();
  game->gpu.gpu_native_init();
  game->pad.overridesInit();
  render_path_install(core);

  core->r[4] = 1;
  core->r[5] = 0;
  runtime.registerOverrides(*game);
  FrameLoopShell shell;
  shell.prepareProduct(*game);
  runtime.bootInit(*core);

  const int requestedFrames = cfg_int("PSXPORT_NATIVE_FRAMES", 0);
  std::uint32_t frameLimit = requestedFrames > 0 ? static_cast<std::uint32_t>(requestedFrames) : 0u;
  if (frameLimit == 0 && !gpu_windowed()) {
    frameLimit = 120;
  }
  lucent::info("frame", "entering Tekken 3 native-owned frame loop ({})", frameLimit ? "capped" : "interactive");
  for (std::uint32_t frame = 0; frameLimit == 0 || frame < frameLimit; ++frame) {
    shell.step(*core, frame);
  }
  lucent::info("frame", "Tekken 3 frame loop completed after {} frame(s)", frameLimit);
  return 0;
}

} // namespace tekken3
