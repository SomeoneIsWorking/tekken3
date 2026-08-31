#include "recomp_register.h"

#include "core.h"
#include "overlay_table.h"
#include "rec_decls.h"
#include "recomp_iface.h"

extern void shard_set_override(std::uint32_t, void (*)(Core *));

namespace {

const RecompRegistry kTekken3RecompiledProgram = {
    .main_dispatch = main_dispatch,
    .rec_func_index = rec_func_index,
    .overlays = g_rec_overlays,
    .overlay_count = g_rec_overlay_count,
    .shard_set_override = shard_set_override,
    .ov_a00_set_override = nullptr,
    .ov_game_set_override = nullptr,
    .guestMemset_gen = nullptr,
};

const tekken3::RecompiledProgramBindings kTekken3Bindings{
    .mainSuper = gen_func_80028BA0,
    .frameBarrierSuper = gen_func_800296C4,
    .displayInitSuper = gen_func_800B0954,
    .cdSyncSuper = gen_func_80083904,
    .cdReadySuper = gen_func_80083B84,
    .cdControlSuper = gen_func_80083E4C,
    .cdCommandSuper = gen_func_80090D88,
    .cdQueueStartSuper = gen_func_80090F78,
    .cdQueueResultSuper = gen_func_80091328,
    .gpuTimeoutArmSuper = gen_func_8007E8F0,
    .gpuTimeoutPollSuper = gen_func_8007E924,
    .viewDimensionsSuper = gen_func_80080A40,
    .stageClipSuper = gen_func_8006CC28,
    .effectClipSuper = gen_func_8006E44C,
    .setOverride = shard_set_override,
};

} // namespace

namespace tekken3 {

void installRecompiledProgram() {
  psxport_install_recomp(&kTekken3RecompiledProgram);
}

const RecompiledProgramBindings &recompiledProgramBindings() {
  return kTekken3Bindings;
}

} // namespace tekken3
