#include "core.h"
#include "widescreen.h"

#include <cstdint>
#include <cstdio>
#include <memory>

namespace {

GuestProjectionGeometry observedGeometry;
std::uint32_t retailWidth = 0;
std::uint32_t retailHeight = 0;

GuestProjectionPlan wideLatch(Core *, GuestProjectionGeometry geometry) {
  observedGeometry = geometry;
  return guest_projection_plan({
      .path = RenderPath::Gte,
      .requested = PresentationAspect::Wide16x9,
      .nativePresentation = {368, 448},
      .nativeProjection = geometry,
      .sink = {1920, 1080},
      .vramWidth = 1024,
  });
}

void retailDimensions(Core *core) {
  retailWidth = core->r[4];
  retailHeight = core->r[5];
}

bool measuredPresetsRemainDistinct() {
  const GuestProjectionGeometry boot = tekken3::Tekken3Widescreen::measuredGeometry(384, 480);
  const GuestProjectionGeometry alternate = tekken3::Tekken3Widescreen::measuredGeometry(320, 240);
  const GuestProjectionGeometry other = tekken3::Tekken3Widescreen::measuredGeometry(256, 240);
  return boot.extent.width == 384 && boot.extent.height == 480 && boot.drawWidth == 368 &&
         alternate.extent.width == 320 && alternate.extent.height == 240 && alternate.drawWidth == 320 &&
         other.extent.width == 256 && other.extent.height == 240 && other.drawWidth == 256;
}

bool publicationWidesOnlyTheHorizontalOwners() {
  auto core = std::make_unique<Core>();
  core->r[4] = 384;
  core->r[5] = 480;
  tekken3::Tekken3Widescreen widescreen(wideLatch, retailDimensions);
  widescreen.publishDimensions(*core);

  return observedGeometry.extent.width == 384 && observedGeometry.extent.height == 480 &&
         observedGeometry.drawWidth == 368 && retailWidth == 512 && retailHeight == 480;
}

std::uint32_t packedVertex(std::int16_t vertexX, std::int16_t vertexY) {
  return static_cast<std::uint16_t>(vertexX) | (static_cast<std::uint32_t>(static_cast<std::uint16_t>(vertexY)) << 16u);
}

bool wideStageAndEffectMarginsSurviveRetailClip() {
  auto core = std::make_unique<Core>();
  tekken3::Tekken3Widescreen widescreen(wideLatch, retailDimensions);
  core->r[4] = 384;
  core->r[5] = 480;
  widescreen.publishDimensions(*core);

  constexpr std::uint32_t command = 0x80010000u;
  constexpr std::uint32_t packet = 0x80011000u;
  constexpr std::uint32_t orderingTable = 0x80012000u;
  constexpr std::uint32_t state = 0x80013000u;
  core->mem_w32(command, 0x28000000u);
  core->mem_w32(command + 4u, 0x03020100u);
  for (std::uint32_t index = 0; index < 4; ++index) {
    core->mem_w32(0x1F800000u + index * 4u, packedVertex(static_cast<std::int16_t>(400 + index * 8), 100));
  }
  core->mem_w32(orderingTable, 0x00123456u);
  core->mem_w32(state, 1);
  core->mem_w32(state + 4u, 1);
  core->r[4] = command;
  core->r[5] = packet;
  core->r[6] = orderingTable;
  core->r[7] = state;
  widescreen.clipStagePrimitives(*core);
  if (core->mem_r32(state) != 24 || core->mem_r32(state + 4u) != 0 || core->mem_r32(packet) != 0x05123456u ||
      core->mem_r32(orderingTable) != (packet & 0x00FFFFFFu)) {
    return false;
  }

  constexpr std::uint32_t effectCommand = 0x80014000u;
  constexpr std::uint32_t effectPacket = 0x80015000u;
  constexpr std::uint32_t effectOt = 0x80016000u;
  constexpr std::uint32_t effectContext = 0x80017000u;
  core->mem_w32(effectCommand, 6u << 21u);
  core->mem_w32(0x1F800000u, packedVertex(450, 100));
  core->mem_w32(0x1F800004u, packedVertex(450, 100));
  core->mem_w32(0x1F800008u, packedVertex(450, 20));
  core->mem_w32(0x1F80000Cu, packedVertex(450, 100));
  core->mem_w32(effectOt + 24u, 0x000ABCDEu);
  core->mem_w32(effectContext + 12u, 0);
  core->r[4] = effectCommand;
  core->r[5] = effectPacket;
  core->r[6] = effectOt;
  core->r[7] = effectContext;
  widescreen.clipEffectPrimitive(*core);
  return core->mem_r32(effectPacket) == 0x090ABCDEu && core->mem_r32(effectOt + 24u) == (effectPacket & 0x00FFFFFFu);
}

} // namespace

int main() {
  if (!measuredPresetsRemainDistinct() || !publicationWidesOnlyTheHorizontalOwners() ||
      !wideStageAndEffectMarginsSurviveRetailClip()) {
    std::fprintf(stderr,
                 "widescreen_contract: FAIL — Tekken projection publication lost its measured "
                 "view/draw distinction\n");
    return 1;
  }
  std::printf("widescreen_contract: PASS — 384x480/368 and 320x240/320 facts remain distinct; "
              "16:9 widens view 384->512 while preserving height 480, and stage/effect primitives "
              "in the added margin survive retail x=368 clipping\n");
  return 0;
}
