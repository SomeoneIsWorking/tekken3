#include "program/title_runtime.h"

#include "cd/cd_protocol.h"
#include "core.h"
#include "frame/finite_frame.h"
#include "game.h"
#include "render/gpu_queue_timeout.h"

#include <lucent/log.h>

#include <cstdlib>
#include <stdexcept>

namespace {

// FUN_800B0B9C passes each 42-byte pad record's +2 receive buffer to InitPAD (FUN_800946A8).
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

TitleRuntime::TitleRuntime(ResidentProgramRange residentProgram) : programImage_(makeProgramImage(residentProgram)) {}

TitleRuntime::TitleRuntime(ResidentProgramRange residentProgram, std::uint32_t programEntry)
    : programImage_(makeProgramImage(residentProgram)), programEntry_(programEntry) {
  if (programEntry_ == 0) {
    throw std::invalid_argument("Tekken 3 retail program entry is zero");
  }
}

RenderCapabilities TitleRuntime::renderCapabilities() const {
  // The picture is the guest's GP0 output replayed from the frame record; already 60 fps, so no interpolation.
  return RenderCapabilities{
      .defaultPath = RenderPath::Record,
      .nativeRenderPath = false,
      .temporalInterpolation = false,
  };
}

bool TitleRuntime::guestVramIsPicture(const Game &) const {
  return false;
}

const PlatformHlePlan *TitleRuntime::platformHlePlan() const {
  return &hle::plan();
}

const GuestPadBufferLayout *TitleRuntime::guestPadBufferLayout() const {
  return &kGuestPadBufferLayout;
}

const GuestWidescreenProjection *TitleRuntime::guestWidescreenProjection() const {
  return &projection_;
}

void *TitleRuntime::createContext(Core &) {
  return nullptr;
}

void TitleRuntime::destroyContext(void *) {}

void TitleRuntime::registerOverrides(Game &game) {
  auto *const driver = dynamic_cast<frame::FrameDriver *>(game.frameDriver.get());
  if (!driver) {
    lucent::error("overrides", "Tekken 3 override registration has no title frame driver");
    std::abort();
  }
  driver->installOverrides();
  cd::installOverrides(game.core);
  render::installOverrides(game.core);
  projection_.install(game.core);
}

void TitleRuntime::bootInit(Core &core) {
  if (programEntry_ == 0) {
    lucent::error("boot", "no authenticated retail program entry is installed");
    std::abort();
  }
  auto *const driver = core.game ? dynamic_cast<frame::FrameDriver *>(core.game->frameDriver.get()) : nullptr;
  if (!driver) {
    lucent::error("boot", "Tekken 3 finite boot has no title FrameDriver");
    std::abort();
  }
  driver->runBootPrefix(core, programEntry_);
}

std::unique_ptr<FrameDriver> TitleRuntime::createFrameDriver(Game &game) {
  return std::make_unique<frame::FrameDriver>(game);
}

const GuestProgramImage *TitleRuntime::guestProgramImage() const {
  return programImage_.residentText.valid() ? &programImage_ : nullptr;
}

} // namespace tekken3
