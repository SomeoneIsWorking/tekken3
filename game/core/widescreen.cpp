#include "widescreen.h"

#include "core.h"
#include "game.h"
#include "gpu_vk.h"
#include "mods.h"
#include "override_registry.h"
#include "recompiled_program_bindings.h"

#include <array>
#include <cstdlib>
#include <limits>
#include <lucent/log.h>

namespace tekken3 {
namespace {

constexpr std::uint32_t kViewDimensions = 0x80080A40u;
constexpr std::uint32_t kStageClip = 0x8006CC28u;
constexpr std::uint32_t kEffectClip = 0x8006E44Cu;
constexpr std::uint32_t kBootViewWidth = 384u;
constexpr std::uint32_t kBootViewHeight = 480u;
constexpr std::uint32_t kBootDrawWidth = 368u;
constexpr std::uint32_t kAlternateViewWidth = 320u;
constexpr std::uint32_t kAlternateViewHeight = 240u;
constexpr std::uint32_t kAlternateDrawWidth = 320u;
constexpr std::uint32_t kScratch = 0x1F800000u;

std::int16_t x(std::uint32_t packed) {
  return static_cast<std::int16_t>(packed & 0xFFFFu);
}

std::int16_t y(std::uint32_t packed) {
  return static_cast<std::int16_t>(packed >> 16u);
}

std::uint32_t scratchVertex(Core &core, std::uint32_t indices, std::uint32_t index) {
  const std::uint32_t vertexIndex = (indices >> (index * 8u)) & 0xFFu;
  return core.mem_r32(kScratch + vertexIndex * 4u);
}

template <std::size_t Count> bool visible(const std::array<std::uint32_t, Count> &vertices, int right) {
  bool everyAbove = true;
  bool everyLeft = true;
  bool anyInsideRight = false;
  for (const std::uint32_t vertex : vertices) {
    everyAbove = everyAbove && y(vertex) < 0;
    everyLeft = everyLeft && x(vertex) < 0;
    anyInsideRight = anyInsideRight || x(vertex) < right;
  }
  return !everyAbove && !everyLeft && anyInsideRight;
}

void writePacketWord(Core &core, std::uint32_t packet, std::uint32_t index, std::uint32_t value) {
  core.mem_w32(packet + index * 4u, value);
}

void linkPacket(Core &core, std::uint32_t packet, std::uint32_t orderingTable, std::uint32_t words) {
  writePacketWord(core, packet, 0, (core.mem_r32(orderingTable) & 0x00FFFFFFu) | (words << 24u));
  core.mem_w32(orderingTable, packet & 0x00FFFFFFu);
}

const Tekken3Widescreen &policyFrom(Core *core, const char *owner) {
  if (!core || !core->runtime) {
    lucent::error("wide", "Tekken 3 {} override ran without its title runtime", owner);
    std::abort();
  }
  const auto *const policy = dynamic_cast<const Tekken3Widescreen *>(core->runtime->guestWidescreenProjection());
  if (!policy) {
    lucent::error("wide", "Tekken 3 {} override reached another title's policy", owner);
    std::abort();
  }
  return *policy;
}

} // namespace

Tekken3Widescreen::Tekken3Widescreen() : Tekken3Widescreen(gpu_vk_latch_guest_projection) {}

Tekken3Widescreen::Tekken3Widescreen(ProjectionLatch latch) : latch_(latch) {
  if (!latch_) {
    lucent::error("wide", "Tekken 3 projection owner requires the shared plan latch");
    std::abort();
  }
}

Tekken3Widescreen::Tekken3Widescreen(ProjectionLatch latch, GuestBody retailDimensions) : Tekken3Widescreen(latch) {
  if (!retailDimensions) {
    lucent::error("wide", "Tekken 3 projection owner requires the retail dimension body");
    std::abort();
  }
  retailDimensions_ = retailDimensions;
}

PresentationAspect Tekken3Widescreen::presentationAspect(const Core &core) const {
  if (!core.game) {
    return PresentationAspect::Standard4x3;
  }
  switch (core.game->mods.aspect) {
  case ASPECT_4_3:
    return PresentationAspect::Standard4x3;
  case ASPECT_16_9:
    return PresentationAspect::Wide16x9;
  case ASPECT_21_9:
    return PresentationAspect::UltraWide21x9;
  case ASPECT_AUTO:
    return PresentationAspect::MatchSink;
  default:
    lucent::error("wide", "Tekken 3 received invalid aspect selector {}", core.game->mods.aspect);
    std::abort();
  }
}

GuestProjectionGeometry Tekken3Widescreen::measuredGeometry(std::uint32_t viewWidth, std::uint32_t viewHeight) {
  if (viewWidth == kBootViewWidth && viewHeight == kBootViewHeight) {
    return {{static_cast<int>(viewWidth), static_cast<int>(viewHeight)}, static_cast<int>(kBootDrawWidth)};
  }
  if (viewWidth == kAlternateViewWidth && viewHeight == kAlternateViewHeight) {
    return {{static_cast<int>(viewWidth), static_cast<int>(viewHeight)}, static_cast<int>(kAlternateDrawWidth)};
  }
  if (viewWidth == 0 || viewHeight == 0 || viewWidth > static_cast<std::uint32_t>(std::numeric_limits<int>::max()) ||
      viewHeight > static_cast<std::uint32_t>(std::numeric_limits<int>::max())) {
    lucent::error("wide", "Tekken 3 received invalid view dimensions {}x{}", viewWidth, viewHeight);
    std::abort();
  }

  // FUN_800809D8 is a second caller which can publish non-preset render targets. No measured
  // display/projection disparity exists for those inputs, so preserve their authored width.
  return {{static_cast<int>(viewWidth), static_cast<int>(viewHeight)}, static_cast<int>(viewWidth)};
}

void Tekken3Widescreen::install(const RecompiledProgramBindings &bindings) {
  if (!bindings.viewDimensionsSuper || !bindings.stageClipSuper || !bindings.effectClipSuper || !bindings.setOverride) {
    lucent::error("wide", "Tekken 3 product is missing a generated widescreen super or override setter");
    std::abort();
  }
  retailDimensions_ = bindings.viewDimensionsSuper;
  retailStageClip_ = bindings.stageClipSuper;
  retailEffectClip_ = bindings.effectClipSuper;
  overrides::install(
      kViewDimensions, "Tekken3::viewDimensions", publishDimensionsOverride, retailDimensions_, bindings.setOverride);
  overrides::install(kStageClip, "Tekken3::stageClip", stageClipOverride, retailStageClip_, bindings.setOverride);
  overrides::install(kEffectClip, "Tekken3::effectClip", effectClipOverride, retailEffectClip_, bindings.setOverride);
}

void Tekken3Widescreen::publishDimensions(Core &core) const {
  if (!retailDimensions_) {
    lucent::error("wide", "Tekken 3 view dimensions ran before the widescreen owner was installed");
    std::abort();
  }

  const GuestProjectionGeometry native = measuredGeometry(core.r[4], core.r[5]);
  plan_ = latch_(&core, native);
  if (!plan_.projectionExtent.width || plan_.projectionExtent.width > std::numeric_limits<std::uint16_t>::max()) {
    lucent::error("wide", "Tekken 3 received invalid projected width {}", plan_.projectionExtent.width);
    std::abort();
  }

  lucent::info("wide",
               "Tekken 3 view {}x{} / draw {} -> view {}x{} / draw {}",
               native.extent.width,
               native.extent.height,
               native.drawWidth,
               plan_.projectionExtent.width,
               plan_.projectionExtent.height,
               plan_.guestDrawWidth);
  core.r[4] = static_cast<std::uint32_t>(plan_.projectionExtent.width);
  core.r[5] = static_cast<std::uint32_t>(plan_.projectionExtent.height);
  retailDimensions_(&core);
}

void Tekken3Widescreen::clipStagePrimitives(Core &core) const {
  if (!plan_.widescreen()) {
    if (!retailStageClip_) {
      lucent::error("wide", "Tekken 3 stage clip ran before its retail super was installed");
      std::abort();
    }
    retailStageClip_(&core);
    return;
  }

  std::uint32_t command = core.r[4];
  std::uint32_t packet = core.r[5];
  const std::uint32_t orderingTable = core.r[6];
  const std::uint32_t state = core.r[7];
  std::int32_t inputRemaining = static_cast<std::int32_t>(core.mem_r32(state));
  std::int32_t capacityRemaining = static_cast<std::int32_t>(core.mem_r32(state + 4u));
  std::uint32_t producedBytes = 0;

  while (inputRemaining > 0 && capacityRemaining > 0) {
    const std::uint32_t opcode = core.mem_r32(command) & 0xFF000000u;
    std::uint32_t commandWords = 0;
    std::uint32_t packetWords = 0;
    std::array<std::uint32_t, 4> vertices{};

    if (opcode == 0x2C000000u) {
      const std::uint32_t indices = core.mem_r32(command + 16u);
      for (std::uint32_t index = 0; index < 4; ++index) {
        vertices[index] = scratchVertex(core, indices, index);
      }
      commandWords = 5;
      if (visible(vertices, plan_.guestDrawWidth)) {
        packetWords = 10;
        linkPacket(core, packet, orderingTable, 9);
        writePacketWord(core, packet, 1, core.mem_r32(command));
        writePacketWord(core, packet, 2, vertices[0]);
        writePacketWord(core, packet, 3, core.mem_r32(command + 4u));
        writePacketWord(core, packet, 4, vertices[1]);
        writePacketWord(core, packet, 5, core.mem_r32(command + 8u));
        writePacketWord(core, packet, 6, vertices[2]);
        writePacketWord(core, packet, 7, core.mem_r16(command + 12u));
        writePacketWord(core, packet, 8, vertices[3]);
        writePacketWord(core, packet, 9, core.mem_r16(command + 14u));
      }
    } else if (opcode == 0x24000000u) {
      const std::uint32_t indices = core.mem_r32(command + 16u);
      for (std::uint32_t index = 0; index < 3; ++index) {
        vertices[index] = scratchVertex(core, indices, index);
      }
      commandWords = 5;
      const std::array<std::uint32_t, 3> triangle{vertices[0], vertices[1], vertices[2]};
      if (visible(triangle, plan_.guestDrawWidth)) {
        packetWords = 8;
        linkPacket(core, packet, orderingTable, 7);
        writePacketWord(core, packet, 1, core.mem_r32(command));
        writePacketWord(core, packet, 2, vertices[0]);
        writePacketWord(core, packet, 3, core.mem_r32(command + 4u));
        writePacketWord(core, packet, 4, vertices[1]);
        writePacketWord(core, packet, 5, core.mem_r32(command + 8u));
        writePacketWord(core, packet, 6, vertices[2]);
        writePacketWord(core, packet, 7, core.mem_r16(command + 12u));
      }
    } else if (opcode == 0x28000000u) {
      const std::uint32_t indices = core.mem_r32(command + 4u);
      for (std::uint32_t index = 0; index < 4; ++index) {
        vertices[index] = scratchVertex(core, indices, index);
      }
      commandWords = 2;
      if (visible(vertices, plan_.guestDrawWidth)) {
        packetWords = 6;
        linkPacket(core, packet, orderingTable, 5);
        writePacketWord(core, packet, 1, core.mem_r32(command));
        for (std::uint32_t index = 0; index < 4; ++index) {
          writePacketWord(core, packet, index + 2u, vertices[index]);
        }
      }
    }

    if (commandWords != 0) {
      command += commandWords * 4u;
    }
    if (packetWords != 0) {
      packet += packetWords * 4u;
      producedBytes += packetWords * 4u;
      --capacityRemaining;
    }
    --inputRemaining;
  }

  core.mem_w32(state, producedBytes);
  core.mem_w32(state + 4u, static_cast<std::uint32_t>(capacityRemaining));
  core.r[2] = static_cast<std::uint32_t>(capacityRemaining);
}

void Tekken3Widescreen::clipEffectPrimitive(Core &core) const {
  if (!plan_.widescreen()) {
    if (!retailEffectClip_) {
      lucent::error("wide", "Tekken 3 effect clip ran before its retail super was installed");
      std::abort();
    }
    retailEffectClip_(&core);
    return;
  }

  const std::uint32_t command = core.r[4];
  const std::uint32_t packet = core.r[5];
  const std::uint32_t orderingTables = core.r[6];
  const std::uint32_t context = core.r[7];
  const std::array<std::uint32_t, 4> vertices{
      core.mem_r32(kScratch),
      core.mem_r32(kScratch + 4u),
      core.mem_r32(kScratch + 8u),
      core.mem_r32(kScratch + 12u),
  };
  std::int32_t orderingTableIndex = static_cast<std::int32_t>((core.mem_r32(command) >> 21u) & 0x3FFu);
  if ((core.mem_r32(context + 12u) & 0x2000u) != 0) {
    orderingTableIndex -= 5;
  }
  if (x(vertices[0]) > plan_.guestDrawWidth || x(vertices[1]) < 0 || y(vertices[0]) > 468 || y(vertices[2]) < 20 ||
      orderingTableIndex < 0) {
    return;
  }

  const std::uint32_t orderingTable = orderingTables + static_cast<std::uint32_t>(orderingTableIndex) * 4u;
  linkPacket(core, packet, orderingTable, 9);
  writePacketWord(core, packet, 1, core.mem_r32(command));
  for (std::uint32_t index = 0; index < 4; ++index) {
    writePacketWord(core, packet, index * 2u + 2u, vertices[index]);
  }
}

void Tekken3Widescreen::publishDimensionsOverride(Core *core) {
  policyFrom(core, "projection").publishDimensions(*core);
}

void Tekken3Widescreen::stageClipOverride(Core *core) {
  policyFrom(core, "stage clip").clipStagePrimitives(*core);
}

void Tekken3Widescreen::effectClipOverride(Core *core) {
  policyFrom(core, "effect clip").clipEffectPrimitive(*core);
}

} // namespace tekken3
