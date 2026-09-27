// vsync_field_clock.cpp — the one production binding of Tekken's measured VSync field counter to the
// guest's RAM. See vsync_field_clock.h for the reverse-engineering provenance of the address.
#include "vsync_field_clock.h"

#include "core.h"

namespace tekken3::vsync {

std::uint32_t readFieldCounter(Core &core) {
  return core.mem_r32(kFieldCounter);
}

} // namespace tekken3::vsync
