// sync_native.h — Tekken 3's declared hardware-sync primitives (see sync_native.cpp for the RE
// provenance behind every bound address).
#pragma once

struct PlatformHlePlan;

namespace tekken3 {

// The process-immutable plan consumed by PlatformHle::initBuiltins() on this direct runtime.
const PlatformHlePlan &platformHlePlan();

} // namespace tekken3
