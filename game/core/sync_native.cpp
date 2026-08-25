// sync_native.cpp — Tekken 3's declared hardware-sync primitives.
//
// Tekken runs its WHOLE retail program on the substrate, so SCEI library leaves that busy-wait must
// resolve natively. The bindings below are GAME facts, each carrying its RE provenance; the handler
// bodies are the framework's faithful implementations (Timing::vsyncHle), reached through
// GameRuntime::platformHlePlan() -> PlatformHle::initBuiltins() (see platform_hle.h).
#include "sync_native.h"

#include "game_runtime.h"
#include "platform_hle.h"
#include "timing.h"

namespace tekken3 {

namespace {

// libetc VSync(mode): measured at 0x800859A8 in SLUS_004.02.
//
// Provenance (RE FIRST): Ghidra headless decompile of the retail image,
//     external/psxport/tools/decomp.sh decomp tekken3_boot <out> list 0x800859A8
// (project scratch/ghidra/tekken3_boot, retail bytes at load 0x80010000). FUN_800859a8 answers
// mode<0 by returning a vblank counter without waiting, mode>=1 by advancing it — the libetc
// contract — and its only visible caller family is CdSync (FUN_80083b84, strings "CD ready",
// "Sync: ", CdlSync/NoIntr name tables), which spins VSync(-1) against a deadline of
// count + 0x3C0. With no HLE here, that deadline never moves and whole-program boot wedges
// inside the CD wait (tekken3 issue 0011 symptom, pre-seed run log
// scratch/logs/tekken3-port-headless-20260825.log).
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
        p.bindingCount = 1;
        p.bindings[0] = {kVSyncAddr, Timing::vsyncHle};
        p.windowLo[0] = kVSyncAddr;
        p.windowHi[0] = kVSyncBodyEnd;
        return p;
    }();
    return plan;
}

} // namespace tekken3
