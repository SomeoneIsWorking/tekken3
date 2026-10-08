// The stage tile selector's world-space visibility cone (FUN_8006D014), widened in the tangent domain.
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

  /// Selector arguments after the wedge (call sites 0x8006D1EC, 0x8006D274); tileSize is a4 from 16(sp).
  struct Query {
    std::int32_t heading = 0;
    std::int32_t first = 0;
    std::int32_t second = 0;
    std::int32_t tileSize = 0;
  };

  /// Block geometry published by FUN_8006C95C.
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

  /// Why the selection cannot run: guest invariants and the selector's undefined-input paths.
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

  /// Identity for plans that did not widen the projection.
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
