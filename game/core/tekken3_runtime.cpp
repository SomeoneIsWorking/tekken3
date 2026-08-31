#include "tekken3_runtime.h"

#include "cd_sync.h"
#include "core.h"
#include "frame_loop.h"
#include "game.h"
#include "gpu_sync.h"

#include <lucent/log.h>

#include <cstdlib>
#include <stdexcept>

namespace {

// FUN_800B0B9C initializes two 42-byte title pad records and passes each record's +2 receive
// buffer to FUN_800946A8 (Tekken's linked Sony libpad InitPAD implementation).
constexpr GuestPadBufferLayout kGuestPadBufferLayout{
    .slot0Buffer = 0x800A9132u,
    .slot1Buffer = 0x800A915Cu,
};

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

Tekken3Runtime::Tekken3Runtime(ResidentProgramRange residentProgram,
                               std::uint32_t programEntry,
                               const RecompiledProgramBindings &bindings)
    : programImage_(makeProgramImage(residentProgram)), programEntry_(programEntry), bindings_(&bindings) {
  if (programEntry_ == 0) {
    throw std::invalid_argument("Tekken 3 retail program entry is zero");
  }
  if (!bindings.complete()) {
    throw std::invalid_argument("Tekken 3 recompiled program bindings are incomplete");
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

const GuestPadBufferLayout *Tekken3Runtime::guestPadBufferLayout() const {
  return &kGuestPadBufferLayout;
}

const GuestWidescreenProjection *Tekken3Runtime::guestWidescreenProjection() const {
  return &widescreen_;
}

void *Tekken3Runtime::createContext(Core &) {
  return nullptr;
}

void Tekken3Runtime::destroyContext(void *) {}

void Tekken3Runtime::registerOverrides(Game &game) {
  auto *const driver = dynamic_cast<Tekken3FrameDriver *>(game.frameDriver.get());
  if (!driver) {
    lucent::error("frame", "Tekken 3 override registration has no title FrameDriver");
    std::abort();
  }
  driver->installOverrides();
  installCdOverrides(*bindings_);
  installGpuSyncOverrides(*bindings_);
  widescreen_.install(*bindings_);
}

void Tekken3Runtime::bootInit(Core &core) {
  if (programEntry_ == 0) {
    lucent::error("tekken3-runtime",
                  "no retail program entry is installed; interpreter and boundary runtimes cannot "
                  "be used as the whole-program product");
    std::abort();
  }
  auto *const driver = core.game ? dynamic_cast<Tekken3FrameDriver *>(core.game->frameDriver.get()) : nullptr;
  if (!driver) {
    lucent::error("boot", "Tekken 3 finite boot has no title FrameDriver");
    std::abort();
  }
  driver->runBootPrefix(core, programEntry_);
}

std::unique_ptr<FrameDriver> Tekken3Runtime::createFrameDriver(Game &game) {
  return std::make_unique<Tekken3FrameDriver>(game, bindings_);
}

const GuestProgramImage *Tekken3Runtime::guestProgramImage() const {
  return programImage_.residentText.valid() ? &programImage_ : nullptr;
}

} // namespace tekken3
