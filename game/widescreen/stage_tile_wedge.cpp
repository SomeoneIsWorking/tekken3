#include "widescreen/stage_tile_wedge.h"

#include "core.h"
#include "native_dispatch.h"
#include "widescreen/widescreen.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <lucent/log.h>
#include <numbers>

namespace tekken3::widescreen {
namespace {

constexpr std::uint32_t kStageTileSelector = 0x8006D95Cu;
constexpr std::uint32_t kSineTable = 0x8001E8C4u;
constexpr std::uint32_t kCosineTable = 0x8001F0C4u;
constexpr std::uint32_t kFirstTileOrigin = 0x800A8C44u;
constexpr std::uint32_t kSecondTileOrigin = 0x800A8C50u;
constexpr std::uint32_t kStepScale = 0x800A8D70u;
constexpr std::uint32_t kScratch = 0x1F800000u;
/// One full turn of the direction tables (0x8001E8C4 holds round(sin(2*pi*i/4096)*4096)).
constexpr std::int32_t kTurnUnits = 0x1000;
/// Right angle; at or past it a wider frustum is already inside the cone.
constexpr std::int32_t kQuarterTurn = kTurnUnits / 4;
/// Half turn.
constexpr std::int32_t kHalfTurn = kTurnUnits / 2;
constexpr double kRadiansPerTurn = 2.0 * std::numbers::pi;

void originalStageTileSelector(Core *core) {
  psx::cpu::callOriginalToReturn(
      *core, kStageTileSelector, psx::cpu::ExecutionBudget::currentTurn(*core), "Tekken3::stageTileSelector original");
}

void refuse(const char *detail) {
  lucent::error("wide", "Tekken 3 stage-tile wedge: {}", detail);
  std::abort();
}

// 0x8006D9AC: the selector clamps each camera coordinate into [-2*tile, 2*tile), then substitutes
// -3*tile or 3*tile-1, so the cell is one of the 36 (block origin -3*tile).
std::int32_t clampToBlock(std::int32_t coordinate, std::int32_t tile) {
  const std::int64_t twoTile = static_cast<std::int64_t>(tile) * 2;
  if (static_cast<std::int64_t>(coordinate) < -twoTile) {
    return static_cast<std::int32_t>(-3 * static_cast<std::int64_t>(tile));
  }
  if (static_cast<std::int64_t>(coordinate) >= twoTile) {
    return static_cast<std::int32_t>(3 * static_cast<std::int64_t>(tile) - 1);
  }
  return coordinate;
}

// 0x8006DA68: guest `div`, truncating like C++.
std::int32_t blockCoordinate(std::int32_t along, std::int32_t tile) {
  return static_cast<std::int32_t>(static_cast<std::int64_t>(along) / tile);
}

bool insideBlock(std::int32_t coordinate) {
  return coordinate >= 0 && coordinate < static_cast<std::int32_t>(StageTileWedge::kSpan);
}

// 0x8006DA58: direction word times step scale, low 32 bits, shifted right by 15.
std::int32_t stepComponent(std::int32_t stepScale, std::int32_t direction) {
  const std::int32_t product = static_cast<std::int32_t>(static_cast<std::int64_t>(stepScale) * direction);
  return product >> 15;
}

// 0x8006DA68..0x8006DAC8: march one wedge edge from the camera cell, selecting each cell entered.
// The guest loop is unbounded (a zero step would spin), so it is bounded by marchStepBound.
bool marchRay(StageTileWedge::Selection &selection,
              std::int32_t &lastRow,
              std::int32_t &lastColumn,
              std::int32_t first,
              std::int32_t second,
              const StageTileWedge::StageBlock &block,
              const StageTileWedge::Ray &ray,
              std::int32_t tile,
              std::int64_t maxSteps) {
  std::int32_t along = first - block.firstOrigin;
  std::int32_t across = second - block.secondOrigin;
  bool entered = false;
  for (std::int64_t step = 0; step < maxSteps; ++step) {
    const std::int32_t column = blockCoordinate(along, tile);
    const std::int32_t row = blockCoordinate(across, tile);
    if (!insideBlock(column) || !insideBlock(row)) {
      return entered;
    }
    selection.select(static_cast<std::size_t>(row) * StageTileWedge::kSpan + static_cast<std::size_t>(column));
    lastRow = row;
    lastColumn = column;
    entered = true;
    along += ray.firstStep;
    across += ray.secondStep;
  }
  return entered;
}

// Iterations a march needs to leave the block, ceil(6*tile/|step|)+1; 0 when neither axis moves.
std::int64_t marchStepBound(const StageTileWedge::Ray &ray, std::int32_t tile) {
  const std::int64_t span = static_cast<std::int64_t>(StageTileWedge::kSpan) * tile;
  std::int64_t bound = 0;
  for (const std::int32_t component : {ray.firstStep, ray.secondStep}) {
    const std::int64_t magnitude = component < 0 ? -static_cast<std::int64_t>(component) : component;
    if (magnitude == 0) {
      continue;
    }
    const std::int64_t steps = (span + magnitude - 1) / magnitude + 1;
    if (bound == 0 || steps < bound) {
      bound = steps;
    }
  }
  return bound;
}

// 0x8006DBC4..0x8006DC7C: walk the block border between the two exit cells. The branch pair at
// 0x8006DC54/0x8006DC5C is a back edge; the periodic border is bounded by two laps.
bool walkBorder(StageTileWedge::Selection &selection,
                std::int32_t fromRow,
                std::int32_t fromColumn,
                std::int32_t toRow,
                std::int32_t toColumn) {
  const std::int32_t last = static_cast<std::int32_t>(StageTileWedge::kSpan) - 1;
  // The border holds 4 * (kSpan - 1) cells.
  constexpr int kLaps = 2;
  const int maxSteps = kLaps * 4 * (static_cast<int>(StageTileWedge::kSpan) - 1);
  std::int32_t row = fromRow;
  std::int32_t column = fromColumn;
  for (int step = 0; step < maxSteps; ++step) {
    if (row == last && column < last) {
      ++column;
      selection.select(static_cast<std::size_t>(row) * StageTileWedge::kSpan + static_cast<std::size_t>(column));
      if (column == toColumn && toRow == row) {
        return true;
      }
    }
    if (column == last && row > 0) {
      --row;
      selection.select(static_cast<std::size_t>(row) * StageTileWedge::kSpan + static_cast<std::size_t>(last));
      if (row == toRow && toColumn == column) {
        return true;
      }
    }
    if (row == 0 && column > 0) {
      --column;
      selection.select(static_cast<std::size_t>(column));
      if (column == toColumn && toRow == 0) {
        return true;
      }
    }
    if (column == 0 && row < last) {
      ++row;
      selection.select(static_cast<std::size_t>(row) * StageTileWedge::kSpan);
      if (row == toRow && toColumn == 0) {
        return true;
      }
    }
  }
  return false;
}

// 0x8006DC88..0x8006DD0C: fill each row between selected cells.
void fillRows(StageTileWedge::Selection &selection) {
  for (std::size_t row = 0; row < StageTileWedge::kSpan; ++row) {
    for (std::size_t column = 0; column + 1 < StageTileWedge::kSpan; ++column) {
      if (selection.cell[row * StageTileWedge::kSpan + column] == 0) {
        continue;
      }
      for (std::size_t right = StageTileWedge::kSpan - 1; right > column + 1; --right) {
        if (selection.cell[row * StageTileWedge::kSpan + right] == 0) {
          continue;
        }
        for (std::size_t fill = column; fill < right; ++fill) {
          selection.cell[row * StageTileWedge::kSpan + fill] = 1u;
        }
      }
    }
  }
}

// 0x8006DEAC: Manhattan distance from the camera cell, or kUnreached when not selected.
std::int32_t blockDistance(const StageTileWedge::Selection &selection,
                           std::int32_t cameraColumn,
                           std::int32_t cameraRow,
                           std::int32_t column,
                           std::int32_t row) {
  if (selection.cell[static_cast<std::size_t>(row) * StageTileWedge::kSpan + static_cast<std::size_t>(column)] == 0) {
    return StageTileWedge::kUnreached;
  }
  return std::abs(column - cameraColumn) + std::abs(row - cameraRow);
}

} // namespace

void StageTileWedge::install(Core &core) {
  retailSelector_ = originalStageTileSelector;
  psx::cpu::installNativeOverride(core, kStageTileSelector, "Tekken3::stageTileSelector", selectTilesOverride);
}

void StageTileWedge::publishPlan(const GuestProjectionPlan &plan) const {
  plan_ = plan;
}

std::int32_t StageTileWedge::widenWedge(std::int32_t retailWedge, int nativeProjectionWidth, int projectionWidth) {
  if (retailWedge <= 0 || nativeProjectionWidth <= 0 || projectionWidth <= nativeProjectionWidth) {
    return retailWedge;
  }
  const std::int32_t half = retailWedge >> 1;
  if (half >= kQuarterTurn) {
    // A right-angle cone already covers any wider frustum.
    return retailWedge;
  }
  const double halfAngle = static_cast<double>(half) * kRadiansPerTurn / static_cast<double>(kTurnUnits);
  const double widened = std::atan(std::tan(halfAngle) * static_cast<double>(projectionWidth) /
                                   static_cast<double>(nativeProjectionWidth));
  const double index = widened * static_cast<double>(kTurnUnits) / kRadiansPerTurn;
  const long long rounded = std::llround(index);
  const long long bounded = std::clamp(rounded, 1LL, static_cast<long long>(kHalfTurn));
  return static_cast<std::int32_t>(bounded) << 1;
}

std::int32_t StageTileWedge::directionIndex(std::int32_t heading, std::int32_t halfWedge, bool positive) {
  // 0x8006D9F0/0x8006DAD0: negated heading plus or minus the half wedge, masked to one turn.
  const std::int32_t offset = positive ? halfWedge : -halfWedge;
  return (-heading + offset) & (kTurnUnits - 1);
}

StageTileWedge::Ray StageTileWedge::stepOf(DirectionWord direction, const StageBlock &block) {
  return {stepComponent(block.stepScale, direction.sine), stepComponent(block.stepScale, direction.cosine)};
}

StageTileWedge::Wedge
StageTileWedge::wedgeFor(std::int32_t wedge, const StageBlock &block, DirectionWord left, DirectionWord right) {
  return {stepOf(left, block), stepOf(right, block)};
}

StageTileWedge::Result StageTileWedge::select(const Query &query, const StageBlock &block, const Wedge &wedge) {
  Result result;
  const std::int32_t tile = query.tileSize;
  if (tile <= 0) {
    result.status = SelectionStatus::noTileSize;
    return result;
  }
  if (block.stepScale == 0) {
    result.status = SelectionStatus::noStepScale;
    return result;
  }

  Selection &selection = result.selection;
  const std::int32_t first = clampToBlock(query.first, tile);
  const std::int32_t second = clampToBlock(query.second, tile);

  std::int32_t leftRow = 0;
  std::int32_t leftColumn = 0;
  const std::int64_t leftBound = marchStepBound(wedge.left, tile);
  const std::int64_t rightBound = marchStepBound(wedge.right, tile);
  if (leftBound == 0 || rightBound == 0) {
    result.status = SelectionStatus::marchUnbounded;
    return result;
  }
  if (!marchRay(selection, leftRow, leftColumn, first, second, block, wedge.left, tile, leftBound)) {
    // The -3*tile origin rules this out; the guest would walk from stale registers.
    result.status = SelectionStatus::cameraOutsideBlock;
    return result;
  }
  std::int32_t rightRow = 0;
  std::int32_t rightColumn = 0;
  marchRay(selection, rightRow, rightColumn, first, second, block, wedge.right, tile, rightBound);
  if (!walkBorder(selection, leftRow, leftColumn, rightRow, rightColumn)) {
    result.status = SelectionStatus::borderWalkUnbounded;
    return result;
  }
  fillRows(selection);

  const std::int32_t cameraColumn = blockCoordinate(first - block.firstOrigin, tile);
  const std::int32_t cameraRow = blockCoordinate(second - block.secondOrigin, tile);
  selection.cell[static_cast<std::size_t>(cameraRow) * kSpan + static_cast<std::size_t>(cameraColumn)] = kCameraCell;

  // 0x8006DD78..0x8006DE18: near-ring threshold from cells (2..3, 2..3).
  std::int32_t nearRing = kUnreached;
  for (const std::int32_t row : {2, 3}) {
    for (const std::int32_t column : {2, 3}) {
      const std::int32_t distance = blockDistance(selection, cameraColumn, cameraRow, column, row);
      if (distance < nearRing) {
        nearRing = distance;
      }
    }
  }
  // 0x8006DE20..0x8006DE78: drop selected cells no further than the threshold.
  for (std::size_t row = 0; row < kSpan; ++row) {
    for (std::size_t column = 0; column < kSpan; ++column) {
      if (selection.cell[row * kSpan + column] == 0) {
        continue;
      }
      if (blockDistance(
              selection, cameraColumn, cameraRow, static_cast<std::int32_t>(column), static_cast<std::int32_t>(row)) <=
          nearRing) {
        selection.cell[row * kSpan + column] = 0u;
      }
    }
  }
  return result;
}

std::int32_t StageTileWedge::derivedWedge(std::int32_t retailWedge) const {
  return widenWedge(retailWedge, plan_.nativeProjectionExtent.width, plan_.projectionExtent.width);
}

const GuestProjectionPlan &StageTileWedge::plan() const {
  return plan_;
}

StageTileWedge::DirectionWord StageTileWedge::guestDirection(Core &core, std::int32_t index) {
  // `lh` at 0x8006DA14/0x8006DA2C: sign-extend.
  const std::uint32_t offset = static_cast<std::uint32_t>(index) * 2u;
  return {static_cast<std::int32_t>(static_cast<std::int16_t>(core.mem_r16(kSineTable + offset))),
          static_cast<std::int32_t>(static_cast<std::int16_t>(core.mem_r16(kCosineTable + offset)))};
}

void StageTileWedge::selectTiles(Core &core) const {
  if (!plan_.widescreen()) {
    if (!retailSelector_) {
      lucent::error("wide", "Tekken 3 stage tile selector ran before its retail super was installed");
      std::abort();
    }
    retailSelector_(&core);
    return;
  }

  // Stack arguments in the caller's frame: a4 tile size at 16(sp), a5 block bitmap at 20(sp).
  const std::uint32_t callerStack = core.r[29];
  const Query query{
      .heading = static_cast<std::int32_t>(core.r[5]),
      .first = static_cast<std::int32_t>(core.r[6]),
      .second = static_cast<std::int32_t>(core.r[7]),
      .tileSize = static_cast<std::int32_t>(core.mem_r32(callerStack + 16u)),
  };
  const std::uint32_t grid = core.mem_r32(callerStack + 20u);
  const StageBlock block{
      .firstOrigin = static_cast<std::int32_t>(core.mem_r32(kFirstTileOrigin)),
      .secondOrigin = static_cast<std::int32_t>(core.mem_r32(kSecondTileOrigin)),
      .stepScale = static_cast<std::int32_t>(core.mem_r32(kStepScale)),
  };

  const std::int32_t retailWedge = static_cast<std::int32_t>(core.r[4]);
  const std::int32_t wedge = derivedWedge(retailWedge);
  const std::int32_t half = wedge >> 1;
  const Wedge rays = wedgeFor(wedge,
                              block,
                              guestDirection(core, directionIndex(query.heading, half, false)),
                              guestDirection(core, directionIndex(query.heading, half, true)));
  const Result result = select(query, block, rays);
  switch (result.status) {
  case SelectionStatus::ok:
    break;
  case SelectionStatus::noTileSize:
    refuse("the stage published no tile size, so its tile selector has no block to divide");
  case SelectionStatus::noStepScale:
    refuse("the stage published no direction step scale");
  case SelectionStatus::marchUnbounded:
    refuse("a wedge edge has no direction step, so the guest's tile march could not leave the block");
  case SelectionStatus::cameraOutsideBlock:
    refuse("the camera cell is outside the published tile block, so the guest's border walk is undefined");
  case SelectionStatus::borderWalkUnbounded:
    refuse("the guest's tile-block border walk never reached the second wedge edge and would spin");
  }
  for (std::size_t index = 0; index < kCells; ++index) {
    core.mem_w32(grid + static_cast<std::uint32_t>(index) * 4u, result.selection.cell[index]);
  }
  lucent::debug("wide", "Tekken 3 stage tile wedge {} -> {} at heading {}", retailWedge, wedge, query.heading);
}

void StageTileWedge::selectTilesOverride(Core *core) {
  policyFrom(core, "stage tile selector").stageWedge().selectTiles(*core);
}

} // namespace tekken3::widescreen
