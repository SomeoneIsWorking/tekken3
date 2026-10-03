// stage_tile_wedge.h — the last horizontal culling owner: the stage-tile visibility wedge.
//
// The title's stage owner FUN_8006D014 hands an authored horizontal wedge (600, or 780 for its
// alternate mode) to the 6x6 stage-tile selector FUN_8006D95C, which returns one word per block
// cell: 0 culled, 1 selected, and 0xFFFFFFFE for the cell the camera stands in. The wedge reaches
// the selector as the first argument, and the selector only ever uses it as `wedge >> 1` — a heading
// in a 0x1000-unit turn (0x8006D960) that indexes the title's own Q12 direction tables
// (0x8001E8C4 sine, 0x8001F0C4 cosine; 0x1000 is one full turn) to give the two rays it marches
// (0x8006D9F0 and 0x8006DAD0). It is a world-space direction cone, never a screen-space extent: no
// focal length, view width, or draw width appears anywhere in the selection.
//
// A wider frustum therefore does not rescale the wedge, it needs the wedge to keep covering the
// frustum. The projection widens the view half-width at an unchanged focal length H, and screen
// x = H*tan(theta), so the horizontal half-extent that a fixed H admits scales exactly in the
// tangent domain. `widenWedge` applies the plan's own widening factor there, which is the unique
// factor that preserves the cone's coverage of the frustum at every focal length.
#pragma once

#include "guest_widescreen_projection.h"

#include <array>
#include <cstddef>
#include <cstdint>

class Core;

namespace tekken3::widescreen {

class WidescreenProjection;

class StageTileWedge final {
public:
  static constexpr std::size_t kSpan = 6;
  static constexpr std::size_t kCells = kSpan * kSpan;
  /// 0x7FFF: the guest's "no selected cell" distance (0x8006DEAC).
  static constexpr std::int32_t kUnreached = 0x7FFF;
  /// 0xFFFFFFFE: the guest's marker for the cell the camera stands in (0x8006DD48).
  static constexpr std::uint32_t kCameraCell = 0xFFFFFFFEu;

  using GuestBody = void (*)(Core *);

  /// The selector's arguments after its wedge, recovered from the guest call sites 0x8006D1EC and
  /// 0x8006D274: a1 camera heading, a2 first world coordinate, a3 second world coordinate, and
  /// a4 stage tile size from the caller's 16(sp) argument slot.
  struct Query {
    std::int32_t heading = 0;
    std::int32_t first = 0;
    std::int32_t second = 0;
    std::int32_t tileSize = 0;
  };

  /// The block geometry the stage initializer FUN_8006C95C publishes: the two tile-block origins and
  /// the direction step scale, from tile units of the stage descriptor's second field.
  struct StageBlock {
    std::int32_t firstOrigin = 0;
    std::int32_t secondOrigin = 0;
    std::int32_t stepScale = 0;
  };

  /// One word of the title's Q12 direction tables, amplitude 4096.
  struct DirectionWord {
    std::int32_t sine = 0;
    std::int32_t cosine = 0;
  };

  /// The per-ray step the selector adds to its running block coordinate each iteration.
  struct Ray {
    std::int32_t firstStep = 0;
    std::int32_t secondStep = 0;
  };

  struct Wedge {
    Ray left;
    Ray right;
  };

  struct Selection {
    std::array<std::uint32_t, kCells> cell{};

    void select(std::size_t index) {
      cell[index] = 1u;
    }
  };

  /// Why the recovered selection cannot run. These are guest invariants the title's own stage
  /// initializer establishes, and the selector's undefined-input paths; the runtime owner reports
  /// them and the contract pins each one.
  enum class SelectionStatus {
    ok,
    noTileSize,
    noStepScale,
    marchUnbounded,
    cameraOutsideBlock,
    borderWalkUnbounded,
  };

  struct Result {
    SelectionStatus status = SelectionStatus::ok;
    Selection selection;
  };

  void install(Core &core);
  void publishPlan(const GuestProjectionPlan &plan) const;
  void selectTiles(Core &core) const;
  [[nodiscard]] std::int32_t derivedWedge(std::int32_t retailWedge) const;
  [[nodiscard]] const GuestProjectionPlan &plan() const;

  /// Widen one authored wedge for a resolved plan. The identity — the exact retail argument — for
  /// every plan that did not widen the projection.
  static std::int32_t widenWedge(std::int32_t retailWedge, int nativeProjectionWidth, int projectionWidth);
  static std::int32_t directionIndex(std::int32_t heading, std::int32_t halfWedge, bool positive);
  static Ray stepOf(DirectionWord direction, const StageBlock &block);
  static Wedge wedgeFor(std::int32_t wedge, const StageBlock &block, DirectionWord left, DirectionWord right);
  static Result select(const Query &query, const StageBlock &block, const Wedge &wedge);

private:
  static void selectTilesOverride(Core *core);
  static DirectionWord guestDirection(Core &core, std::int32_t index);

  GuestBody retailSelector_ = nullptr;
  mutable GuestProjectionPlan plan_;
};

} // namespace tekken3::widescreen
