#include "core.h"
#include "game.h"
#include "game_iface.h"

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
void tekken3_main_prefix(Core *core);

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
  std::fflush(stdout);
  std::exit(EXIT_SUCCESS);
}

} // namespace

// The shipping emitter derives this symbol from the executable's measured first-call target. If
// that target changes, the generated TU names a different symbol and the link refuses instead of
// silently capturing the old boundary.
void func_80079D10(Core *core) {
  core->pc = 0x80079D10U;
  captureBoundary(core);
}

int main(int argc, char **argv) {
  if (argc != 5) {
    std::fprintf(stderr, "usage: %s <PS-X EXE> <entry> <direct-main> <boundary>\n", argv[0]);
    return 2;
  }

  const std::uint32_t entry = parseAddress(argv[2], "entry");
  const std::uint32_t directMain = parseAddress(argv[3], "direct-main");
  const std::uint32_t boundary = parseAddress(argv[4], "boundary");

  static const GameConfig config{};
  static const GameHooks hooks{};
  psxport_install_game(&config, &hooks);

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

  tekken3_main_prefix(core);
  std::fprintf(stderr, "FAIL: generated prefix returned without reaching boundary 0x%08X\n", boundary);
  return 1;
}
