#include "tekken3_runtime.h"

#include "core.h"

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

Tekken3Runtime::Tekken3Runtime(ResidentProgramRange residentProgram, std::uint32_t programEntry)
    : programImage_(makeProgramImage(residentProgram)), programEntry_(programEntry) {
  if (programEntry_ == 0) {
    throw std::invalid_argument("Tekken 3 retail program entry is zero");
  }
}

RenderCapabilities Tekken3Runtime::renderCapabilities() const {
  return RenderCapabilities::widescreenOnly();
}

bool Tekken3Runtime::guestVramIsPicture(const Game &) const {
  // Tekken's verified boundary harness produces no picture. Widescreen remains on the shared guest
  // projection path; this boundary must not claim an implicit framebuffer before a frame is proven.
  return false;
}

const PlatformHlePlan *Tekken3Runtime::platformHlePlan() const {
  // The measured SCEI library bindings (sync_native.cpp holds each address's RE provenance).
  return &tekken3::platformHlePlan();
}

void *Tekken3Runtime::createContext(Core &) {
  return nullptr;
}

void Tekken3Runtime::destroyContext(void *) {}

void Tekken3Runtime::registerOverrides(Game &) {
  // The verified T3-04 slice has no native game overrides. The independently checked
  // interrupt-controller sequence remains generated execution rather than being bypassed here.
}

[[noreturn]] void Tekken3Runtime::bootInit(Core &core) {
  if (programEntry_ == 0) {
    lucent::error("tekken3-runtime",
                  "no retail program entry is installed; interpreter and boundary runtimes cannot "
                  "be used as the whole-program product");
    std::abort();
  }
  lucent::info("boot", "dispatching Tekken 3 retail entry 0x{:08X} on the recompiled substrate", programEntry_);
  rec_dispatch(&core, programEntry_);
  lucent::error("tekken3-runtime", "retail entry 0x{:08X} returned past its terminating break", programEntry_);
  std::abort();
}

const GuestProgramImage *Tekken3Runtime::guestProgramImage() const {
  return programImage_.residentText.valid() ? &programImage_ : nullptr;
}

} // namespace tekken3
