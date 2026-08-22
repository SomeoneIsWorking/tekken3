#include "tekken3_runtime.h"

#include <lucent/log.h>

#include <cstdlib>
#include <stdexcept>

namespace {

GuestProgramImage makeProgramImage(tekken3::ResidentProgramRange range) {
  if (range.hi <= range.lo) {
    throw std::invalid_argument("Tekken 3 resident program range is empty or inverted");
  }
  return {
      .residentText = {range.lo, range.hi},
  };
}

} // namespace

namespace tekken3 {

Tekken3Runtime::Tekken3Runtime(ResidentProgramRange residentProgram)
    : programImage_(makeProgramImage(residentProgram)) {}

void *Tekken3Runtime::createContext(Core &) {
  return nullptr;
}

void Tekken3Runtime::destroyContext(void *) {}

void Tekken3Runtime::registerOverrides(Game &) {
  // The verified T3-04 slice has no native game overrides. The independently checked
  // interrupt-controller sequence remains generated execution rather than being bypassed here.
}

[[noreturn]] void Tekken3Runtime::bootInit(Core &) {
  lucent::error("tekken3-runtime",
                "whole-program boot is not implemented; the verified execution frontier stops "
                "after the interrupt-controller reset sequence at T3-04");
  std::abort();
}

const GuestProgramImage *Tekken3Runtime::guestProgramImage() const {
  return programImage_.residentText.valid() ? &programImage_ : nullptr;
}

} // namespace tekken3
