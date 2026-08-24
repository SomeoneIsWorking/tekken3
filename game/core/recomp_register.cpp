#include "recomp_register.h"

#include "core.h"
#include "overlay_table.h"
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

} // namespace

namespace tekken3 {

void installRecompiledProgram() {
  psxport_install_recomp(&kTekken3RecompiledProgram);
}

} // namespace tekken3
