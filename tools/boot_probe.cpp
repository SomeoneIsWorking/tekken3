// Execute a bounded PS-X EXE entry window in psxport's interpreter and capture the register file
// immediately before a caller-supplied direct-main boundary. The boundary address comes from the
// game-owned executable manifest; this probe deliberately knows no libc/InitHeap vocabulary.
#include "core.h"
#include "game.h"
#include "tekken3_runtime.h"

#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>

void load_exe(const char *path, Core *core);
void interp_coro_run(Core *core, uint32_t pc);

namespace {
constexpr std::array<const char *, 32> kRegisterNames = {
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0",   "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
};

struct BoundaryReached final {};

struct Capture {
  std::array<uint32_t, 32> registers{};
  uint32_t hi = 0;
  uint32_t lo = 0;
  uint32_t pc = 0;
  uint64_t observerOrdinal = 0;
  bool reached = false;
};

uint32_t parseAddress(const char *text, const char *label) {
  errno = 0;
  char *end = nullptr;
  const unsigned long value = std::strtoul(text, &end, 0);
  if (errno != 0 || !end || *end != '\0' || value > UINT32_MAX) {
    std::fprintf(stderr, "boot_probe: REFUSED — %s is not a uint32 address: %s\n", label, text);
    std::exit(2);
  }
  return static_cast<uint32_t>(value);
}

void captureBoundary(Core *core, uint64_t ordinal, uint32_t guestPc, void *user) {
  auto &capture = *static_cast<Capture *>(user);
  for (size_t index = 0; index < capture.registers.size(); ++index) {
    capture.registers[index] = core->r[index];
  }
  capture.hi = core->hi;
  capture.lo = core->lo;
  capture.pc = guestPc;
  capture.observerOrdinal = ordinal;
  capture.reached = true;
  throw BoundaryReached{};
}

void usage() {
  std::fprintf(stderr, "usage: tekken3_boot_probe <PS-X EXE> --entry 0xADDR --boundary 0xADDR\n");
}
} // namespace

int main(int argc, char **argv) {
  const char *executable = nullptr;
  uint32_t entry = 0;
  uint32_t boundary = 0;
  bool haveEntry = false;
  bool haveBoundary = false;

  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "--entry") == 0 && index + 1 < argc) {
      entry = parseAddress(argv[++index], "--entry");
      haveEntry = true;
    } else if (std::strcmp(argv[index], "--boundary") == 0 && index + 1 < argc) {
      boundary = parseAddress(argv[++index], "--boundary");
      haveBoundary = true;
    } else if (argv[index][0] == '-') {
      usage();
      return 2;
    } else if (!executable) {
      executable = argv[index];
    } else {
      usage();
      return 2;
    }
  }
  if (!executable || !haveEntry || !haveBoundary) {
    usage();
    return 2;
  }

  // This interpreter-only probe needs no resident generated-code range, but it still installs the
  // same derived runtime owner as every Tekken executable before constructing a Core.
  static tekken3::Tekken3Runtime runtime;
  psxport_install_game(runtime);

  auto game = std::make_unique<Game>();
  Core *const core = &game->core;
  core->use_interp = 1;
  load_exe(executable, core);

  Capture capture;
  if (!core->pcObserver.arm(&boundary, 1, captureBoundary, &capture)) {
    std::fprintf(stderr, "boot_probe: REFUSED — could not arm the direct-main boundary observer\n");
    return 2;
  }

  try {
    interp_coro_run(core, entry);
  } catch (const BoundaryReached &) {
    // The observer fires before the target instruction executes: this is the same post-delay-slot
    // call boundary emitted by oracle_trace's CAPTURED-CALL block.
  }
  core->pcObserver.disarm();

  if (!capture.reached) {
    std::fprintf(stderr, "boot_probe: REFUSED — execution returned without reaching boundary 0x%08X\n", boundary);
    return 2;
  }

  std::printf("# PSXPORT-BOUNDARY pc=0x%08X observer-ordinal=%llu\n",
              capture.pc,
              static_cast<unsigned long long>(capture.observerOrdinal));
  for (size_t index = 0; index < capture.registers.size(); ++index) {
    std::printf("# PSXPORT-REG %s=0x%08X\n", kRegisterNames[index], capture.registers[index]);
  }
  std::printf("# PSXPORT-REG lo=0x%08X\n", capture.lo);
  std::printf("# PSXPORT-REG hi=0x%08X\n", capture.hi);
  std::printf("boot_probe: PASS — captured 35 fields before direct-main 0x%08X\n", capture.pc);
  std::printf("boot_probe: NOT covered — generated substrate, BIOS, devices, frames, or gameplay\n");
  return 0;
}
