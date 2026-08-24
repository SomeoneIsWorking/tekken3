#include "tekken3_runtime.h"

#include "config_var.h"
#include "config_vars.h"
#include "core.h"
#include "render_mode.h"

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

bool Tekken3Runtime::configureRenderPath() {
  psx::config::cv_render_path.set(psx::config::Layer::Default, render_path_name(RenderPath::Gte));
  const RenderPath selected = psx::config::render_path();
  if (selected != RenderPath::Gte && selected != RenderPath::Psx) {
    lucent::error("tekken3-render",
                  "render path '{}' is unsupported before Tekken owns native picture producers; "
                  "select 'gte' for the retail geometry stream or 'psx' for the software reference",
                  render_path_name(selected));
    return false;
  }
  return true;
}

bool Tekken3Runtime::guestVramIsPicture(const Game &) const {
  // Tekken's verified boundary harness produces no picture. Future widescreen ownership is native;
  // guest VRAM must not become an implicit fallback for an unimplemented frame.
  return false;
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
