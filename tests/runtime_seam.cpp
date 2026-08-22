#include "core.h"
#include "tekken3_runtime.h"

#include <cstdint>
#include <cstdio>
#include <memory>
#include <stdexcept>

namespace {

constexpr tekken3::ResidentProgramRange kFixtureRange{0x00001000u, 0x00002000u};

} // namespace

int main() {
  bool invalidRangeRefused = false;
  try {
    tekken3::Tekken3Runtime invalid{{0x00010000u, 0x00010000u}};
  } catch (const std::invalid_argument &) {
    invalidRangeRefused = true;
  }
  if (!invalidRangeRefused) {
    std::fprintf(stderr, "runtime_seam: FAIL — an empty resident program range was accepted\n");
    return 1;
  }

  static tekken3::Tekken3Runtime runtime{kFixtureRange};
  psxport_install_game(runtime);

  // Core owns the complete 2 MiB guest RAM plus device state and is intentionally heap-resident in
  // every production Game. Keep this seam check on the same lifetime path.
  auto core = std::make_unique<Core>();
  if (core->runtime != &runtime) {
    std::fprintf(stderr, "runtime_seam: FAIL — Core did not snapshot the derived Tekken runtime\n");
    return 1;
  }
  if (!core->cfg || core->cfg->recMainLo != kFixtureRange.lo || core->cfg->recMainHi != kFixtureRange.hi) {
    std::fprintf(stderr, "runtime_seam: FAIL — resident program facts did not reach the legacy router view\n");
    return 1;
  }
  if (core->gameCtx != nullptr) {
    std::fprintf(stderr, "runtime_seam: FAIL — an empty legacy context was unexpectedly created\n");
    return 1;
  }

  std::printf("runtime_seam: PASS — Core owns the derived runtime, 2/2 resident-range facts reach "
              "the bounded legacy router view, and 1/1 invalid range is refused\n");
  std::printf("runtime_seam: NOT covered — I_MASK execution, devices, frames, or gameplay\n");
  return 0;
}
