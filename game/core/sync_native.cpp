// sync_native.cpp — Tekken 3's declared hardware-sync primitives.
//
// Tekken's native frame driver owns cadence, so guest code must never advance the host clock through
// libetc VSync. The declaration below is GAME data; PlatformHle owns the mandatory fatal handler and
// deliberately gives the title no replaceable function pointer for it.
#include "sync_native.h"

#include "game_runtime.h"
#include "platform_hle.h"
#include "vsync_field_clock.h"

namespace tekken3 {

const PlatformHlePlan &platformHlePlan() {
  static const PlatformHlePlan plan = [] {
    PlatformHlePlan p{};
    p.vsyncAddress = vsync::kEntry;
    // Tekken calls VSync 22 times and 21 of those pass a negative mode, so they are QUERIES for the
    // field count rather than waits. PlatformHle answers a negative query only from this declared
    // word and refuses explicitly without one; it is the same word the guest's own leaf returns, so
    // the framework's answer and the guest's answer cannot disagree. The single waiting call site,
    // FUN_800B0954's leading VSync(0), is inside a function the title already owns natively. The
    // window admits exactly the one bound leaf, so engine text stays refused by construction.
    p.vsyncQueryCounterAddress = vsync::kFieldCounter;
    p.windowLo[0] = vsync::kEntry;
    p.windowHi[0] = vsync::kBodyEnd;
    return p;
  }();
  return plan;
}

} // namespace tekken3
