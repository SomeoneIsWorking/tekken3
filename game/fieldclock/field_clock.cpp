#include "fieldclock/field_clock.h"

#include "core.h"

namespace tekken3::field {

std::uint32_t readCounter(Core &core) {
  return core.mem_r32(kCounter);
}

} // namespace tekken3::field
