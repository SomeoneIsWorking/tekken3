// platform_hle_plan.h — the hardware-sync leaves this title declares to the framework.
//
// Tekken's native frame driver owns cadence, so guest code must never advance the host clock through
// linked libetc VSync. What the title declares here is DATA — the measured addresses — never a
// function pointer: PlatformHle owns the handler and its mandatory fatal path.
#pragma once

struct PlatformHlePlan;

namespace tekken3::hle {

// The process-immutable declaration consumed by PlatformHle::initBuiltins() on this direct runtime.
const PlatformHlePlan &plan();

} // namespace tekken3::hle
