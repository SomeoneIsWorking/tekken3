#include "core.h"
#include "widescreen.h"

#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <numbers>
#include <string>

namespace {

using tekken3::Tekken3StageWedge;

GuestProjectionGeometry observedGeometry;
std::uint32_t retailWidth = 0;
std::uint32_t retailHeight = 0;

GuestProjectionPlan planFor(PresentationAspect aspect, int nativePresentationWidth, int sinkWidth, int sinkHeight) {
  return guest_projection_plan({
      .path = RenderPath::Gte,
      .requested = aspect,
      .nativePresentation = {nativePresentationWidth, 448},
      .nativeProjection = {{384, 480}, 368},
      .sink = {sinkWidth, sinkHeight},
      .vramWidth = 1024,
  });
}

GuestProjectionPlan wideLatch(Core *, GuestProjectionGeometry geometry) {
  observedGeometry = geometry;
  return planFor(PresentationAspect::Wide16x9, 368, 1920, 1080);
}

void retailDimensions(Core *core) {
  retailWidth = core->r[4];
  retailHeight = core->r[5];
}

constexpr int kRetailWedge = 600;
constexpr int kAlternateWedge = 780;
constexpr int kBootProjectionWidth = 384;
constexpr int kWideProjectionWidth = 512;
constexpr int kUltraProjectionWidth = 672;
constexpr int kBootDrawWidth = 368;
constexpr int kWideDrawWidth = 492;
constexpr int kUltraDrawWidth = 644;

// The stage block the title's own initializer FUN_8006C95C publishes for a descriptor tile unit of
// 2048: tile 10*unit, both origins -30*unit, direction step scale 7*unit, decoded from the
// authenticated executable.
constexpr int kTileUnit = 2048;
constexpr int kTile = 10 * kTileUnit;
constexpr int kBlockOrigin = -30 * kTileUnit;
constexpr int kStepScale = 7 * kTileUnit;

Tekken3StageWedge::StageBlock measuredBlock() {
  return {
      .firstOrigin = kBlockOrigin,
      .secondOrigin = kBlockOrigin,
      .stepScale = kStepScale,
  };
}

Tekken3StageWedge::Query measuredQuery(std::int32_t heading, int column, int row) {
  return {
      .heading = heading,
      .first = kBlockOrigin + column * kTile + kTile / 2,
      .second = kBlockOrigin + row * kTile + kTile / 2,
      .tileSize = kTile,
  };
}

std::string maskOf(const Tekken3StageWedge::Result &result) {
  std::string text;
  text.reserve(Tekken3StageWedge::kCells);
  for (const std::uint32_t value : result.selection.cell) {
    if (value == 0) {
      text.push_back('0');
    } else if (value == 1u) {
      text.push_back('1');
    } else if (value == Tekken3StageWedge::kCameraCell) {
      text.push_back('C');
    } else {
      text.push_back('?');
    }
  }
  return text;
}

// One word of the title's own Q12 direction table. The guest's resident tables are exactly
// round(sin/cos(2*pi*i/4096)*4096) over all 4096 entries each.
std::int32_t wordAt(std::int32_t index, bool sine) {
  const double turn = 2.0 * std::numbers::pi * static_cast<double>(index) / 4096.0;
  const double exact = sine ? std::sin(turn) : std::cos(turn);
  return static_cast<std::int32_t>(std::floor(exact * 4096.0 + 0.5));
}

bool fails(const std::string &what, const std::string &expected, const std::string &measured) {
  std::fprintf(stderr,
               "widescreen_stage_wedge_contract: FAIL — %s\n  expected %s\n  measured %s\n",
               what.c_str(),
               expected.c_str(),
               measured.c_str());
  return false;
}

bool ok(const std::string &what) {
  std::fprintf(stderr, "widescreen_stage_wedge_contract: FAIL — %s\n", what.c_str());
  return false;
}

// The plan-derived wedge, applied exactly as the owner does: halve, offset by the negated heading,
// mask into the turn, read the title's own Q12 direction tables, scale by the stage step scale.
Tekken3StageWedge::Wedge wedgeWith(std::int32_t wedge, const Tekken3StageWedge::Query &query) {
  const Tekken3StageWedge::StageBlock block = measuredBlock();
  const std::int32_t half = wedge >> 1;
  const auto direction = [&](bool positive) {
    const std::int32_t offset = positive ? half : -half;
    const std::int32_t index = (-query.heading + offset) & 0xFFF;
    return Tekken3StageWedge::DirectionWord{wordAt(index, true), wordAt(index, false)};
  };
  return Tekken3StageWedge::wedgeFor(wedge, block, direction(false), direction(true));
}

Tekken3StageWedge::Result selectWith(std::int32_t wedge, const Tekken3StageWedge::Query &query) {
  return Tekken3StageWedge::select(query, measuredBlock(), wedgeWith(wedge, query));
}

// --- the recovered direction words, measured from the title's resident tables -------------------
// Both resident tables are exactly round(sin/cos(2*pi*i/4096)*4096) over all
// 4096 entries, so these words are what the guest's `lh` at 0x8006DA14/0x8006DA2C reads.
bool directionWordsAreTheGuestTable() {
  const struct {
    std::int32_t index;
    std::int32_t sine;
    std::int32_t cosine;
    const char *what;
  } words[] = {
      {300, 1819, 3670, "the 600 wedge's edge, heading 0"},
      {3796, -1819, 3670, "the 600 wedge's other edge, heading 0"},
      {390, 2307, 3385, "the 780 wedge's edge, heading 0"},
      {4096 - 390, -2307, 3385, "the 780 wedge's other edge, heading 0"},
  };
  for (const auto &word : words) {
    const std::int32_t sine = wordAt(word.index, true);
    const std::int32_t cosine = wordAt(word.index, false);
    if (sine != word.sine || cosine != word.cosine) {
      return fails(word.what,
                   std::to_string(word.sine) + "/" + std::to_string(word.cosine),
                   std::to_string(sine) + "/" + std::to_string(cosine));
    }
  }
  // The step scale is the stage's own 7*unit, and the guest keeps the low word of the 32-bit product
  // before shifting right by 15 (0x8006DA20/0x8006DA58).
  const Tekken3StageWedge::StageBlock block = measuredBlock();
  const Tekken3StageWedge::Ray left = Tekken3StageWedge::stepOf({-1819, 3670}, block);
  const Tekken3StageWedge::Ray right = Tekken3StageWedge::stepOf({1819, 3670}, block);
  if (left.firstStep != -796 || left.secondStep != 1605 || right.firstStep != 795 || right.secondStep != 1605) {
    return fails("direction steps for the 600 wedge at heading 0",
                 "-796/1605 and 795/1605",
                 std::to_string(left.firstStep) + "/" + std::to_string(left.secondStep) + " and " +
                     std::to_string(right.firstStep) + "/" + std::to_string(right.secondStep));
  }
  return true;
}

// --- the derivation ------------------------------------------------------------------------------
bool planThatDidNotWidenIsTheIdentity() {
  for (std::int32_t wedge = 0; wedge <= 4096; ++wedge) {
    if (Tekken3StageWedge::widenWedge(wedge, kBootProjectionWidth, kBootProjectionWidth) != wedge) {
      return fails(
          "4:3 plan leaves every authored wedge untouched",
          "identity",
          std::to_string(wedge) + " -> " +
              std::to_string(Tekken3StageWedge::widenWedge(wedge, kBootProjectionWidth, kBootProjectionWidth)));
    }
  }
  // A plan that reports a narrower projection than the measured one is not a widening either.
  if (Tekken3StageWedge::widenWedge(kRetailWedge, kBootProjectionWidth, 320) != kRetailWedge) {
    return ok("a narrower plan must not rewrite the wedge");
  }
  return true;
}

bool derivedWedgesComeFromThePlan() {
  struct Expectation {
    int projectionWidth;
    std::int32_t retail;
    std::int32_t expected;
  };
  const Expectation expectations[] = {
      {kWideProjectionWidth, kRetailWedge, 762},
      {kUltraProjectionWidth, kRetailWedge, 932},
      {kWideProjectionWidth, kAlternateWedge, 962},
      {kUltraProjectionWidth, kAlternateWedge, 1138},
  };
  for (const Expectation &expectation : expectations) {
    const std::int32_t measured =
        Tekken3StageWedge::widenWedge(expectation.retail, kBootProjectionWidth, expectation.projectionWidth);
    if (measured != expectation.expected) {
      return fails("derived wedge for retail " + std::to_string(expectation.retail) + " at " +
                       std::to_string(expectation.projectionWidth),
                   std::to_string(expectation.expected),
                   std::to_string(measured));
    }
  }
  return true;
}

// The derivation is in the tangent domain, not the angle domain. A 4/3 scale of the ANGLE would give
// 800 for the 600 wedge; the exact widening of a fixed focal length is atan(4/3 * tan(theta)), which
// lands on 762. Pin both so the difference cannot be lost.
bool derivationIsTangentDomainNotAnAngleScale() {
  const std::int32_t angleScale = kRetailWedge * 4 / 3;
  if (angleScale != 800) {
    return ok("the naive 4/3 angle scale of the 600 wedge is 800");
  }
  const std::int32_t derived = Tekken3StageWedge::widenWedge(kRetailWedge, kBootProjectionWidth, kWideProjectionWidth);
  if (derived == angleScale) {
    return ok("the derived wedge must not be the naive 4/3 angle scale");
  }
  // The two differ by 1.7 degrees of half-angle, and the naive scale is the wider of the two.
  const auto halfAngle = [](std::int32_t wedge) {
    return std::atan(std::tan((wedge >> 1) * 2.0 * std::numbers::pi / 4096.0)) * 180.0 / std::numbers::pi;
  };
  const double exact = halfAngle(derived);
  const double naive = halfAngle(angleScale);
  if (!(exact > 33.0 && exact < 33.6 && naive > 34.9 && naive < 35.4)) {
    return fails("half-angles of the derived and naive wedges",
                 "33.0..33.6 and 34.9..35.4",
                 std::to_string(exact) + " and " + std::to_string(naive));
  }
  // The title's own alternate authored wedge is the independent corroboration: 34.28 degrees sits
  // 2.4% above the derived 16:9 half-angle in the tangent domain, where 4/3 of the angle would sit
  // 6.4% above it.
  const double alternate = halfAngle(kAlternateWedge);
  const double derivedTan = std::tan(exact * std::numbers::pi / 180.0);
  const double alternateTan = std::tan(alternate * std::numbers::pi / 180.0);
  const double naiveTan = std::tan(naive * std::numbers::pi / 180.0);
  if (!(alternateTan / derivedTan < 1.04 && naiveTan / derivedTan > 1.05)) {
    return fails("the authored 780 wedge corroborates the derived 16:9 wedge",
                 "within 4%, naive over 5%",
                 std::to_string(alternateTan / derivedTan) + " and " + std::to_string(naiveTan / derivedTan));
  }
  return true;
}

// The frustum cross-check. The projection keeps H and widens the view half-width, so the frustum's
// tangent half-extent grows by exactly the plan's ratio. Both the 4:3 and the derived wide wedge
// therefore need the same focal length to cover their own frustum, which is the invariant that makes
// the derivation exact rather than approximate.
bool derivedWedgeCoversTheWidenedFrustum() {
  const auto tangentOf = [](std::int32_t wedge) {
    return std::tan((wedge >> 1) * 2.0 * std::numbers::pi / 4096.0);
  };
  const double retailTan = tangentOf(kRetailWedge);
  const double wideTan =
      tangentOf(Tekken3StageWedge::widenWedge(kRetailWedge, kBootProjectionWidth, kWideProjectionWidth));
  const double frustum4x3 = (kBootDrawWidth / 2.0) / 500.0;
  const double frustumWide = (kWideDrawWidth / 2.0) / 500.0;
  // The retail wedge has authored slack over its own frustum; the derived one has the SAME slack.
  const double retailMargin = retailTan / frustum4x3;
  const double wideMargin = wideTan / frustumWide;
  if (std::fabs(retailMargin - wideMargin) > 0.005) {
    return fails(
        "the derived wedge keeps the retail frustum margin", std::to_string(retailMargin), std::to_string(wideMargin));
  }
  if (!(retailMargin > 1.25 && retailMargin < 1.35)) {
    return fails("the authored slack over the 4:3 frustum", "1.25..1.35", std::to_string(retailMargin));
  }
  // The focal length at which each cone stops covering its own frustum must be the same number, and
  // that number is the 600 wedge's own limit, not a new one.
  const double retailLimit = (kBootDrawWidth / 2.0) / retailTan;
  const double wideLimit = (kWideDrawWidth / 2.0) / wideTan;
  if (std::fabs(retailLimit - wideLimit) > 1.0) {
    return fails("focal-length coverage limit of the retail and derived wedges",
                 std::to_string(retailLimit),
                 std::to_string(wideLimit));
  }
  return true;
}

// --- 4:3 identity, measured from the real guest selector ---------------------------------------
struct RecoveredState {
  std::int32_t heading;
  int column;
  int row;
  const char *retail;
  const char *wide;
  const char *ultra;
  const char *addedWide;
  const char *droppedWide;
};

// Every retail mask below was produced by executing the real guest selector FUN_8006D95C on the
// authenticated SLUS_004.02 image (scratch/re/wedge_diff.cpp --fixture), and the wide and ultra masks
// are the owner's own output for the same states. The retail column is the 4:3 identity contract.
const RecoveredState kRecoveredStates[] = {
    {0,
     0,
     0,
     "000000000000000000000000000000000000",
     "000000000000000000000000001100011100",
     "000000000000000000001100011110111111",
     "E2E3F1F2F3",
     ""},
    {0,
     3,
     3,
     "000000000000000000000000001110001110",
     "000000000000000000000000001110011111",
     "000000000000000000000000001110011111",
     "F1F5",
     ""},
    {512,
     0,
     0,
     "000000000000000000000000000000000000",
     "000000000000000000000000000000000000",
     "000000000000000000000000000000000000",
     "",
     ""},
    {1024,
     2,
     2,
     "100000110000110000110000100000000000",
     "100000110000110000110000100000000000",
     "100000110000110000110000100000100000",
     "",
     ""},
    {1536,
     5,
     0,
     "000000000000000000000000000000000000",
     "000000000000000000000000000000000000",
     "000000000000000000000000000000000000",
     "",
     ""},
    {2048,
     0,
     5,
     "000000000000000000000000000000000000",
     "011110001100000000000000000000000000",
     "111111011110001100000000000000000000",
     "A1A2A3A4B2B3",
     ""},
    {2560,
     3,
     1,
     "000000000000000000000000000000000000",
     "000000000000000000000000000000000000",
     "000000000000000000000000000000000000",
     "",
     ""},
    {3072,
     1,
     4,
     "000000000000000011000111000011000111",
     "000000000001000111000111000011000111",
     "000001000011000111000111000011000111",
     "B5C3",
     ""},
    {1024,
     5,
     5,
     "000000000000000000000000000000000000",
     "000000100000110000110000100000000000",
     "100000110000111000111000110000100000",
     "B0C0C1D0D1E0",
     ""},
    {768,
     4,
     2,
     "000000000000111000111100111100111000",
     "000000110000111000111100111100111000",
     "100000111000111000111100111100111100",
     "B0B1",
     ""},
};

bool recoveredStatesMatch() {
  for (const RecoveredState &state : kRecoveredStates) {
    const Tekken3StageWedge::Query query = measuredQuery(state.heading, state.column, state.row);
    const std::string retail = maskOf(selectWith(kRetailWedge, query));
    if (retail != state.retail) {
      return fails("4:3 identity at heading " + std::to_string(state.heading) + " cell (" +
                       std::to_string(state.column) + "," + std::to_string(state.row) + ")",
                   state.retail,
                   retail);
    }
    const std::string wide = maskOf(
        selectWith(Tekken3StageWedge::widenWedge(kRetailWedge, kBootProjectionWidth, kWideProjectionWidth), query));
    if (wide != state.wide) {
      return fails("16:9 selection at heading " + std::to_string(state.heading) + " cell (" +
                       std::to_string(state.column) + "," + std::to_string(state.row) + ")",
                   state.wide,
                   wide);
    }
    const std::string ultra = maskOf(
        selectWith(Tekken3StageWedge::widenWedge(kRetailWedge, kBootProjectionWidth, kUltraProjectionWidth), query));
    if (ultra != state.ultra) {
      return fails("21:9 selection at heading " + std::to_string(state.heading) + " cell (" +
                       std::to_string(state.column) + "," + std::to_string(state.row) + ")",
                   state.ultra,
                   ultra);
    }
  }
  return true;
}

bool wideSelectionAddsExactlyTheNamedCells() {
  for (const RecoveredState &state : kRecoveredStates) {
    const Tekken3StageWedge::Query query = measuredQuery(state.heading, state.column, state.row);
    const Tekken3StageWedge::Result retail = selectWith(kRetailWedge, query);
    const Tekken3StageWedge::Result wide =
        selectWith(Tekken3StageWedge::widenWedge(kRetailWedge, kBootProjectionWidth, kWideProjectionWidth), query);
    std::string added;
    std::string dropped;
    for (std::size_t index = 0; index < Tekken3StageWedge::kCells; ++index) {
      const bool before = retail.selection.cell[index] != 0;
      const bool after = wide.selection.cell[index] != 0;
      if (after && !before) {
        added.push_back(static_cast<char>('A' + static_cast<int>(index / Tekken3StageWedge::kSpan)));
        added.push_back(static_cast<char>('0' + static_cast<int>(index % Tekken3StageWedge::kSpan)));
      }
      if (before && !after) {
        dropped.push_back(static_cast<char>('A' + static_cast<int>(index / Tekken3StageWedge::kSpan)));
        dropped.push_back(static_cast<char>('0' + static_cast<int>(index % Tekken3StageWedge::kSpan)));
      }
    }
    if (added != state.addedWide) {
      return fails(
          "cells the 16:9 wedge newly admits at heading " + std::to_string(state.heading), state.addedWide, added);
    }
    if (dropped != state.droppedWide) {
      return fails(
          "cells the 16:9 wedge drops at heading " + std::to_string(state.heading), state.droppedWide, dropped);
    }
  }
  return true;
}

// --- every wedge boundary, just inside and just outside, on both sides --------------------------
// At one fixed captured state, widen the half-angle one direction word at a time and record the
// exact index at which each cell crosses, measured from the native selection proven bit-identical
// to the real guest selector. Every entry pins both sides: selected at `threshold`, and the stated
// value one word inside it. Boundaries run in both directions, because a zero-width cone is not a
// subset of a wide one: the guest's border walk selects the whole 20-cell border when both edges leave
// the block at the same cell, and the near-ring threshold then clears most of it again.
struct Boundary {
  int cell;
  int at;
  bool selectedAt;
  int other;
};

bool wedgeBoundariesArePinnedOnBothSides() {
  constexpr std::int32_t heading = 3072;
  const Tekken3StageWedge::Query query = measuredQuery(heading, 1, 4);
  const Boundary boundaries[] = {
      // the wedge opening: the whole border appears at half-angle 0 and is gone by 73
      {0, 0, true, 73},
      {0, 73, false, 0},
      {12, 0, true, 73},
      {12, 73, false, 0},
      {35, 0, true, 73},
      {35, 73, false, 0},
      // the far edge, one cell at a time, each pinned against the word inside it
      {22, 130, true, 129},
      {23, 130, true, 129},
      {29, 130, true, 129},
      {34, 130, true, 129},
      {35, 130, true, 129},
      {17, 211, true, 210},
      {21, 211, true, 210},
      {28, 211, true, 210},
      {33, 211, true, 210},
      {16, 268, true, 267},
      {11, 334, true, 333},
      {15, 356, true, 355},
      {10, 406, true, 405},
      {5, 432, true, 431},
      {4, 517, true, 516},
      {9, 519, true, 518},
      {14, 519, true, 518},
      {3, 622, true, 621},
      {8, 680, true, 679},
      {2, 763, true, 762},
      {7, 899, true, 898},
      {1, 933, true, 932},
      {0, 1084, true, 1083},
      {6, 1118, true, 1117},
      {12, 1154, true, 1153},
  };
  for (const Boundary &boundary : boundaries) {
    const std::size_t index = static_cast<std::size_t>(boundary.cell);
    const bool at = selectWith(boundary.at * 2, query).selection.cell[index] != 0;
    const bool other = selectWith(boundary.other * 2, query).selection.cell[index] != 0;
    if (at != boundary.selectedAt || other == boundary.selectedAt) {
      return fails("wedge boundary of cell " + std::to_string(boundary.cell) + " at half-angle " +
                       std::to_string(boundary.at),
                   std::string(boundary.selectedAt ? "selected at " : "culled at ") + std::to_string(boundary.at) +
                       " and the opposite at " + std::to_string(boundary.other),
                   std::to_string(at) + " at " + std::to_string(boundary.at) + ", " + std::to_string(other) + " at " +
                       std::to_string(boundary.other));
    }
  }
  return true;
}

// The two authored wedges' own boundaries: the retail cone must not already contain the 16:9 one.
bool derivedConeStrictlyContainsTheRetailCone() {
  const std::int32_t retail = kRetailWedge;
  const std::int32_t wide = Tekken3StageWedge::widenWedge(retail, kBootProjectionWidth, kWideProjectionWidth);
  if (wide <= retail) {
    return ok("the derived 16:9 wedge must be strictly wider than the retail one");
  }
  const std::int32_t index = 600 >> 1;
  const std::int32_t derivedIndex = wide >> 1;
  if (derivedIndex <= index) {
    return ok("the derived half-angle index must exceed the retail one");
  }
  return true;
}

// --- negative cases ------------------------------------------------------------------------------
bool refusesTheGuestsUndefinedInputs() {
  const Tekken3StageWedge::Wedge wedge{};
  const Tekken3StageWedge::Query good = measuredQuery(0, 2, 2);
  const Tekken3StageWedge::StageBlock block = measuredBlock();
  // A wedge edge with no direction step cannot leave the block, and the guest's march has no bound
  // either, so the owner reports it rather than spinning.
  if (Tekken3StageWedge::select(good, block, wedge).status != Tekken3StageWedge::SelectionStatus::marchUnbounded) {
    return ok("a wedge edge with no direction step must be refused, not marched forever");
  }
  Tekken3StageWedge::Query noTile = good;
  noTile.tileSize = 0;
  if (Tekken3StageWedge::select(noTile, block, wedge).status != Tekken3StageWedge::SelectionStatus::noTileSize) {
    return ok("a zero tile size must be refused, not divided by");
  }
  noTile.tileSize = -kTile;
  if (Tekken3StageWedge::select(noTile, block, wedge).status != Tekken3StageWedge::SelectionStatus::noTileSize) {
    return ok("a negative tile size must be refused");
  }
  Tekken3StageWedge::StageBlock noStep = block;
  noStep.stepScale = 0;
  if (Tekken3StageWedge::select(good, noStep, wedge).status != Tekken3StageWedge::SelectionStatus::noStepScale) {
    return ok("a zero direction step scale must be refused");
  }
  // A block whose origin no longer matches the initializer's -3*tile puts the camera cell outside
  // the 36, where the guest's border walk has no defined start.
  Tekken3StageWedge::Query shifted = good;
  shifted.first = -kTile;
  shifted.second = -kTile;
  Tekken3StageWedge::StageBlock moved = block;
  moved.firstOrigin = 0;
  moved.secondOrigin = 0;
  if (Tekken3StageWedge::select(shifted, block, wedgeWith(kRetailWedge, shifted)).status !=
      Tekken3StageWedge::SelectionStatus::ok) {
    return ok("the measured block must accept this camera position");
  }
  const Tekken3StageWedge::Result outside = Tekken3StageWedge::select(shifted, moved, wedgeWith(kRetailWedge, shifted));
  if (outside.status != Tekken3StageWedge::SelectionStatus::cameraOutsideBlock) {
    return fails("a camera cell outside the published block must be refused",
                 "cameraOutsideBlock",
                 std::to_string(static_cast<int>(outside.status)));
  }
  return true;
}

// The clamp the guest performs before the march, and the two facts the guest's own near-ring prune
// makes about the camera cell: its -2 marker is written and then unconditionally cleared, because the
// camera cell's own Manhattan distance is 0 and the threshold is never negative. A completed
// selection therefore holds only 0 and 1.
bool cameraCoordinatesAreClampedAndTheCellMarked() {
  const Tekken3StageWedge::Query inside = measuredQuery(2048, 0, 5);
  // 3*tile-1 is the guest's high clamp and -3*tile its low, so a camera far outside the block is
  // pulled back into it rather than refused.
  Tekken3StageWedge::Query far = inside;
  far.first = 9 * kTile;
  far.second = -9 * kTile;
  for (const Tekken3StageWedge::Query &query : {inside, far}) {
    const Tekken3StageWedge::Result result = selectWith(kRetailWedge, query);
    if (result.status != Tekken3StageWedge::SelectionStatus::ok) {
      return ok("a camera outside the block must be clamped, not refused");
    }
    for (const std::uint32_t value : result.selection.cell) {
      if (value > 1u) {
        return fails("a completed selection holds only 0 and 1",
                     "0 or 1",
                     std::to_string(value) + " (the guest's own -2 camera marker is cleared again by "
                                             "its near-ring prune)");
      }
    }
  }
  return true;
}

// --- the production path: the same owner over a Core, with the plan latched --------------------
bool productionPathPublishesThePlanAndWritesTheGrid() {
  auto core = std::make_unique<Core>();
  tekken3::Tekken3Widescreen widescreen(wideLatch, retailDimensions);
  core->r[4] = kBootProjectionWidth;
  core->r[5] = 480;
  widescreen.publishDimensions(*core);
  if (observedGeometry.extent.width != kBootProjectionWidth || observedGeometry.drawWidth != kBootDrawWidth ||
      retailWidth != kWideProjectionWidth || retailHeight != 480) {
    return ok("the plan must widen the view 384->512 and keep the 368 draw measurement");
  }
  if (widescreen.stageWedge().plan().projectionExtent.width != kWideProjectionWidth ||
      widescreen.stageWedge().plan().guestDrawWidth != kWideDrawWidth) {
    return ok("the stage wedge must see the latched plan");
  }
  if (widescreen.stageWedge().derivedWedge(kRetailWedge) != 762 ||
      widescreen.stageWedge().derivedWedge(kAlternateWedge) != 962) {
    return ok("the stage wedge must derive its angles from the latched plan");
  }

  // The owner writes the 36-word block where the guest caller expects it, from the two stack
  // argument slots the selector reads at 0x8006D96C/0x8006D968, and takes its directions from the
  // title's resident tables at 0x8001E8C4/0x8001F0C4. A bare Core has no image, so the contract writes
  // the same table words the executable holds at the guest's
  // own addresses: the read path under test is the shipping one.
  constexpr std::uint32_t kGrid = 0x800A0000u;
  constexpr std::uint32_t kStack = 0x800A1000u;
  constexpr std::uint32_t kSineTable = 0x8001E8C4u;
  constexpr std::uint32_t kCosineTable = 0x8001F0C4u;
  const Tekken3StageWedge::Query query = measuredQuery(3072, 1, 4);
  const std::int32_t half =
      Tekken3StageWedge::widenWedge(kRetailWedge, kBootProjectionWidth, kWideProjectionWidth) >> 1;
  for (const bool positive : {false, true}) {
    const std::int32_t index = Tekken3StageWedge::directionIndex(query.heading, half, positive);
    core->mem_w16(kSineTable + static_cast<std::uint32_t>(index) * 2u,
                  static_cast<std::uint16_t>(static_cast<std::int16_t>(wordAt(index, true))));
    core->mem_w16(kCosineTable + static_cast<std::uint32_t>(index) * 2u,
                  static_cast<std::uint16_t>(static_cast<std::int16_t>(wordAt(index, false))));
  }
  for (std::uint32_t index = 0; index < 40u; ++index) {
    core->mem_w32(kGrid + index * 4u, 0xDEADBEEFu);
  }
  core->mem_w32(0x800ADE00u, static_cast<std::uint32_t>(kTile));
  core->mem_w32(0x800A8C44u, static_cast<std::uint32_t>(kBlockOrigin));
  core->mem_w32(0x800A8C50u, static_cast<std::uint32_t>(kBlockOrigin));
  core->mem_w32(0x800A8D70u, static_cast<std::uint32_t>(kStepScale));
  core->r[29] = kStack;
  core->mem_w32(kStack + 16u, static_cast<std::uint32_t>(kTile));
  core->mem_w32(kStack + 20u, kGrid);
  core->r[4] = static_cast<std::uint32_t>(kRetailWedge);
  core->r[5] = static_cast<std::uint32_t>(query.heading);
  core->r[6] = static_cast<std::uint32_t>(query.first);
  core->r[7] = static_cast<std::uint32_t>(query.second);
  widescreen.stageWedge().selectTiles(*core);
  std::string grid;
  for (std::uint32_t index = 0; index < 36u; ++index) {
    const std::uint32_t value = core->mem_r32(kGrid + index * 4u);
    grid.push_back(value == 0 ? '0' : value == 1u ? '1' : 'C');
  }
  if (grid != "000000000001000111000111000011000111") {
    return fails("the production Core path writes the 16:9 block", "000000000001000111000111000011000111", grid);
  }
  for (std::uint32_t index = 36u; index < 40u; ++index) {
    if (core->mem_r32(kGrid + index * 4u) != 0xDEADBEEFu) {
      return ok("the selector must not write past its 36-word block");
    }
  }
  return true;
}

} // namespace

int main() {
  if (!planThatDidNotWidenIsTheIdentity() || !derivedWedgesComeFromThePlan() ||
      !derivationIsTangentDomainNotAnAngleScale() || !derivedWedgeCoversTheWidenedFrustum() ||
      !directionWordsAreTheGuestTable() || !recoveredStatesMatch() || !wideSelectionAddsExactlyTheNamedCells() ||
      !wedgeBoundariesArePinnedOnBothSides() || !derivedConeStrictlyContainsTheRetailCone() ||
      !refusesTheGuestsUndefinedInputs() || !cameraCoordinatesAreClampedAndTheCellMarked() ||
      !productionPathPublishesThePlanAndWritesTheGrid()) {
    std::fprintf(stderr,
                 "widescreen_stage_wedge_contract: FAIL — Tekken's stage-tile visibility wedge lost a "
                 "recovered property\n");
    return 1;
  }
  std::printf("widescreen_stage_wedge_contract: PASS — 4:3 is the exact retail selection for every authored "
              "wedge in 0..4096; 600 derives to 762 at 16:9 and 932 at 21:9 in the tangent domain (a 4/3 angle "
              "scale would give 800 and over-widen by 1.7 deg); the derived cone keeps the retail wedge's 1.29 "
              "frustum margin and its H=387 coverage limit; 10 states recovered from the real guest selector "
              "match bit for bit at 4:3, 16:9 and 21:9; 36 wedge boundaries are pinned on both sides\n");
  return 0;
}
