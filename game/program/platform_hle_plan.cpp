#include "program/platform_hle_plan.h"

#include "fieldclock/field_clock.h"
#include "platform_hle.h"

namespace tekken3::hle {
namespace {

// Every VSync call outside the title-owned display init passes a negative mode, a field-count query.
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
