#include "core.h"
#include "decompressor_probe.h"

#include <cstdio>
#include <memory>
#include <string>

namespace {

bool contains(const std::string &text, const char *needle) {
  return text.find(needle) != std::string::npos;
}

} // namespace

int main() {
  auto core = std::make_unique<Core>();
  core->r[31] = 0x80028C9Cu;
  core->r[4] = 0x80011000u;
  core->r[5] = 0x80100000u;
  core->r[6] = 4u;
  core->r[7] = 0x800FF800u;
  core->r[9] = 0x800FFE00u;
  auto entry = tekken3::DecompressorProbe::captureEntry(*core, 0x80052CC4u);

  core->r[4] = 0x80011234u;
  core->r[5] = 0x80100040u;
  core->r[6] = 12u;
  core->r[7] = 0x80100020u;
  core->r[9] = 0x80100000u;
  core->r[3] = 5u;
  core->r[31] = 0x8004C71Cu;
  auto reached = tekken3::DecompressorProbe::describe(
      *core, entry, {psx::cpu::ExecutionExitReason::BudgetExhausted, 0x80031C78u, 564482u, "cycle budget exhausted"});
  if (!contains(reached, "guest_call=0x80052CC4 return=0x80028C9C") ||
      !contains(reached, "entry[a0=0x80011000 a1=0x80100000 a2=0x00000004") ||
      !contains(reached, "decompressor_at_exit=1/1") || !contains(reached, "live_lz[ra=0x8004C71C") ||
      !contains(reached, "a0/source=0x80011234(RAM+0x011234)") ||
      !contains(reached, "output_progress=64/1048576 bytes within mapped main RAM") ||
      !contains(reached, "source_progress=unknown(no-lz-entry-sample)") ||
      !contains(reached,
                "copy_progress=copied=5/12 count_within_length=1 length_in_1..32=1 backref_distance=32/2048 "
                "bounded=1")) {
    std::fprintf(stderr, "decompressor_probe_contract: FAIL — reached snapshot lost entry, live pointers, or bounds\n");
    return 1;
  }

  auto unreached = tekken3::DecompressorProbe::describe(
      *core, entry, {psx::cpu::ExecutionExitReason::BudgetExhausted, 0x80052D00u, 32u, "cycle budget exhausted"});
  if (!contains(unreached, "decompressor_at_exit=0/1") || !contains(unreached, "live_lz=unreached-at-exit") ||
      contains(unreached, "output_progress=")) {
    std::fprintf(stderr, "decompressor_probe_contract: FAIL — unreached exit was mistaken for live decompression\n");
    return 1;
  }

  core->r[4] = 0x1F801800u;
  core->r[5] = 0x80200000u;
  core->r[6] = 40u;
  core->r[7] = 0x1F801801u;
  core->r[9] = 0x80100000u;
  core->r[3] = 41u;
  auto invalid = tekken3::DecompressorProbe::describe(
      *core, entry, {psx::cpu::ExecutionExitReason::BudgetExhausted, 0x80031C78u, 64u, "cycle budget exhausted"});
  if (!contains(invalid, "decompressor_at_exit=1/1") || !contains(invalid, "a0/source=0x1F801800(unmapped-main-RAM)") ||
      !contains(invalid, "output_progress=unknown") ||
      !contains(invalid,
                "copy_progress=copied=41/40 count_within_length=0 length_in_1..32=0 "
                "backref_distance=unknown/2048 bounded=0")) {
    std::fprintf(stderr, "decompressor_probe_contract: FAIL — invalid pointers or lengths were reported as bounded\n");
    return 1;
  }

  std::printf("decompressor_probe_contract: PASS — 1/1 reached and 1/1 unreached exits, "
              "1/1 valid mapped copy and 1/1 invalid-pointer/length copy classified\n");
  return 0;
}
