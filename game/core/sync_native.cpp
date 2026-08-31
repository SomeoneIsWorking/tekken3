// sync_native.cpp — Tekken 3's declared hardware-sync primitives.
//
// Tekken's native frame driver owns cadence, so guest code must never advance the host clock through
// libetc VSync. The declaration below is GAME data; PlatformHle owns the mandatory fatal handler and
// deliberately gives the title no replaceable function pointer for it.
#include "sync_native.h"

#include "game_runtime.h"
#include "platform_hle.h"

namespace tekken3 {

namespace {

// libetc VSync(mode): measured at 0x800859A8 in SLUS_004.02.
//
// Provenance (RE FIRST): Ghidra headless decompile of the retail image,
//     external/psxport/tools/decomp.sh decomp tekken3_boot <out> list 0x800859A8
// (project scratch/ghidra/tekken3_boot, retail bytes at load 0x80010000). FUN_800859a8 answers
// mode<0 by returning a vblank counter without waiting and mode>=1 by waiting. The earlier
// Timing::vsyncHle binding let guest code become a second cadence owner; once the native frame loop
// owns finite host turns, every mode is instead a framework-owned fatal ownership violation.
//
// Body extent [0x800859A8, 0x80085B20): adjacent function starts discovered by the recompiler
// (generated/port/shard_disp.c case table: previous entry 0x800858B8, next 0x80085B20). The
// window admits exactly the one bound leaf; engine text stays refused by construction.
constexpr uint32_t kVSyncAddr = 0x800859A8u;
constexpr uint32_t kVSyncBodyEnd = 0x80085B20u;

} // namespace

const PlatformHlePlan &platformHlePlan() {
  static const PlatformHlePlan plan = [] {
    PlatformHlePlan p{};
    p.vsyncAddress = kVSyncAddr;
    p.windowLo[0] = kVSyncAddr;
    p.windowHi[0] = kVSyncBodyEnd;
    return p;
  }();
  return plan;
}

} // namespace tekken3
