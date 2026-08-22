#include "tekken3_runtime.h"

#include "legacy_game_config.h"
#include "legacy_game_hooks.h"

#include <lucent/log.h>

#include <cstdlib>
#include <stdexcept>

namespace {

GameConfig &legacyProgramFacts() {
  // One runtime is installed for the process lifetime. This backing object exists only because the
  // generic resident-code router has not yet migrated recMainLo/recMainHi to a typed fact group.
  static GameConfig facts{};
  return facts;
}

const GameHooks &emptyCompatibilityHooks() {
  // Tekken owns no legacy callback behavior. Tekken3Runtime overrides both adapter methods that
  // would otherwise invoke an unconditional callback; the remaining nullable context callbacks do
  // nothing.
  static const GameHooks hooks{};
  return hooks;
}

GameConfig &bindResidentProgram(tekken3::ResidentProgramRange range) {
  if (range.hi <= range.lo) {
    throw std::invalid_argument("Tekken 3 resident program range is empty or inverted");
  }
  GameConfig &facts = legacyProgramFacts();
  facts.recMainLo = range.lo;
  facts.recMainHi = range.hi;
  return facts;
}

} // namespace

namespace tekken3 {

Tekken3Runtime::Tekken3Runtime() : LegacyGameRuntimeAdapter(legacyProgramFacts(), emptyCompatibilityHooks()) {}

Tekken3Runtime::Tekken3Runtime(ResidentProgramRange residentProgram)
    : LegacyGameRuntimeAdapter(bindResidentProgram(residentProgram), emptyCompatibilityHooks()) {}

void Tekken3Runtime::registerOverrides(Game &) {
  // The verified T3-04 slice has no native game overrides. In particular, the I_MASK access remains
  // the next unexecuted hardware boundary rather than being bypassed here.
}

[[noreturn]] void Tekken3Runtime::bootInit(Core &) {
  lucent::error("tekken3-runtime",
                "whole-program boot is not implemented; the verified execution frontier stops "
                "before the I_MASK access at T3-04");
  std::abort();
}

} // namespace tekken3
