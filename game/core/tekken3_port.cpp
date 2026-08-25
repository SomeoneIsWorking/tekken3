#include "tekken3_port.h"

#include "core.h"
#include "game.h"
#include "recomp_register.h"
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
void gte_init(void);
void load_exe(const char *path, Core *core);
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
  installRecompiledProgram();

  auto game = std::make_unique<Game>();
  // Direct runtimes deliberately have no legacy GameConfig, so bind the title's disc key at the
  // disc subsystem itself. This keeps env/.env/drop-in resolution available without reviving the
  // legacy config adapter.
  game->disc.env_key = "PSXPORT_TEKKEN3_DISC";
  // Game loads persisted configuration, so validate the effective selection only after that layer
  // exists.  Checking earlier would allow a saved native path to replace Tekken's required GTE
  // path between validation and installation.
  if (!runtime.configureRenderPath()) {
    return 2;
  }
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
  // Direct-boot path: native_boot's game_init never runs, so the platform-HLE table must be
  // populated here (same seam Spider-Man drives from its own main; see platform_hle.h). The plan
  // comes from the runtime; initBuiltins announces what it installed either way.
  game->platform_hle.initBuiltins();
  render_path_install(core);

  core->r[4] = 1;
  core->r[5] = 0;
  runtime.registerOverrides(*game);
  runtime.bootInit(*core);
  lucent::info("boot", "Tekken 3 retail entry returned");
  return 0;
}

} // namespace tekken3
