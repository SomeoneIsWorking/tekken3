#include "program/platform_hle_plan.h"

#include "fieldclock/field_clock.h"
#include "platform_hle.h"

namespace tekken3::hle {
namespace {

// Tekken calls VSync 22 times and 21 of those pass a negative mode, so they are queries for the
// field count rather than waits. PlatformHle answers a negative query only from the declared word
// and refuses explicitly without one; it is the same word the guest's own leaf returns, so the
// framework's answer and the guest's cannot disagree. The one waiting call site (FUN_800B0954's
// leading VSync(0)) is inside a function the title already owns natively, and the window admits
// exactly the one bound leaf, so engine text stays refused by construction.
const PlatformHlePlan kPlan{
    .vsyncAddress = field::kEntry,
    .vsyncQueryCounterAddress = field::kCounter,
    .windowLo = {field::kEntry},
    .windowHi = {field::kBodyEnd},
};

} // namespace

const PlatformHlePlan &plan() {
  return kPlan;
}

} // namespace tekken3::hle
