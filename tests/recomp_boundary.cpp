#include "core.h"
#include "game.h"
#include "recomp_iface.h"
#include "tekken3_runtime.h"

#include <array>
#include <charconv>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string_view>
#include <system_error>

void load_exe(const char *path, Core *core);
void interp_coro_run(Core *core, std::uint32_t pc);
void tekken3_main_first_initializer(Core *core);
void tekken3_main_next_initializer_call(Core *core);
std::uint32_t tekken3_initializer_entry_boundary();
std::uint32_t tekken3_initializer_return_boundary();
std::uint32_t tekken3_next_initializer_boundary();
std::uint32_t tekken3_hardware_boundary();
std::uint32_t tekken3_interrupt_reset_boundary();
void tekken3_boundary_main_dispatch(Core *, std::uint32_t);
int tekken3_boundary_func_index(std::uint32_t);

namespace {

constexpr std::array<std::string_view, 32> kRegisterNames = {
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0",   "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
};

std::uint32_t parseAddress(std::string_view text, const char *label) {
  if (text.starts_with("0x") || text.starts_with("0X")) {
    text.remove_prefix(2);
  }
  std::uint32_t value = 0;
  const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value, 16);
  if (error != std::errc{} || end != text.data() + text.size()) {
    std::fprintf(stderr, "REFUSED: %s is not a hexadecimal guest address\n", label);
    std::exit(2);
  }
  return value;
}

struct DirectMainReached final {};

std::uint32_t requestedBoundary = 0;

void stopAtDirectMain(Core *, std::uint64_t, std::uint32_t, void *) {
  throw DirectMainReached{};
}

[[noreturn]] void captureBoundary(Core *core) {
  std::printf("# RECOMP-BOUNDARY pc=0x%08X\n", core->pc);
  for (std::size_t index = 0; index < kRegisterNames.size(); ++index) {
    std::printf("# RECOMP-REG %.*s=0x%08X\n",
                static_cast<int>(kRegisterNames[index].size()),
                kRegisterNames[index].data(),
                core->r[index]);
  }
  std::printf("# RECOMP-REG lo=0x%08X\n", core->lo);
  std::printf("# RECOMP-REG hi=0x%08X\n", core->hi);
  std::printf("# RECOMP-DEVICE I_STAT=0x%03X I_MASK=0x%03X\n", core->game->hle.i_stat, core->game->hle.i_mask);
  std::fflush(stdout);
  std::exit(EXIT_SUCCESS);
}

} // namespace

void tekken3_boundary_hook(Core *core, std::uint32_t boundary) {
  if (boundary == requestedBoundary) {
    core->pc = boundary;
    captureBoundary(core);
  }
}

int main(int argc, char **argv) {
  if (argc != 7) {
    std::fprintf(stderr, "usage: %s <PS-X EXE> <entry> <direct-main> <boundary> <main-lo> <main-hi>\n", argv[0]);
    return 2;
  }

  const std::uint32_t entry = parseAddress(argv[2], "entry");
  const std::uint32_t directMain = parseAddress(argv[3], "direct-main");
  requestedBoundary = parseAddress(argv[4], "boundary");
  const std::uint32_t mainLo = parseAddress(argv[5], "main-lo");
  const std::uint32_t mainHi = parseAddress(argv[6], "main-hi");
  if (mainHi <= mainLo) {
    std::fprintf(stderr, "REFUSED: resident text range is empty or inverted\n");
    return 2;
  }
  if (requestedBoundary != tekken3_initializer_entry_boundary() &&
      requestedBoundary != tekken3_initializer_return_boundary() &&
      requestedBoundary != tekken3_next_initializer_boundary() && requestedBoundary != tekken3_hardware_boundary() &&
      requestedBoundary != tekken3_interrupt_reset_boundary()) {
    std::fprintf(stderr, "REFUSED: unsupported generated boundary 0x%08X\n", requestedBoundary);
    return 2;
  }

  static tekken3::Tekken3Runtime runtime{{mainLo, mainHi}};
  static const RecompRegistry recomp = {
      tekken3_boundary_main_dispatch,
      tekken3_boundary_func_index,
      nullptr,
      0,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
  };
  psxport_install_game(runtime);
  psxport_install_recomp(&recomp);

  auto game = std::make_unique<Game>();
  Core *const core = &game->core;
  core->use_interp = 1;
  load_exe(argv[1], core);
  if (!core->pcObserver.arm(&directMain, 1, stopAtDirectMain, nullptr)) {
    std::fprintf(stderr, "REFUSED: could not arm direct-main 0x%08X\n", directMain);
    return 2;
  }
  try {
    interp_coro_run(core, entry);
  } catch (const DirectMainReached &) {
  }
  core->pcObserver.disarm();
  if (core->pc != directMain) {
    std::fprintf(stderr, "REFUSED: interpreter did not reach direct-main 0x%08X\n", directMain);
    return 2;
  }

  core->use_interp = 0;
  tekken3_main_first_initializer(core);
  tekken3_boundary_hook(core, tekken3_initializer_return_boundary());
  tekken3_main_next_initializer_call(core);
  std::fprintf(stderr, "FAIL: generated slices returned without reaching boundary 0x%08X\n", requestedBoundary);
  return 1;
}
