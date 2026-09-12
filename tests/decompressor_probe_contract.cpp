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
      !contains(reached, "wrapper_entry=unreached") ||
      !contains(reached,
                "copy_progress=copied=5/12 count_within_length=1 length_in_1..32=1 backref_distance=32/2048 "
                "bounded=1")) {
    std::fprintf(stderr, "decompressor_probe_contract: FAIL — reached snapshot lost entry, live pointers, or bounds\n");
    return 1;
  }

  auto unreached = tekken3::DecompressorProbe::describe(
      *core, entry, {psx::cpu::ExecutionExitReason::BudgetExhausted, 0x80052D00u, 32u, "cycle budget exhausted"});
  if (!contains(unreached, "decompressor_at_exit=0/1") || !contains(unreached, "live_lz=unreached-at-exit") ||
      !contains(unreached, "wrapper_entry=unreached") || contains(unreached, "output_progress=")) {
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

  core->r[19] = 0x80080000u; // s3: image table base
  core->r[17] = 0x80080000u; // s1: current eight-byte entry
  core->r[16] = 0u;          // s0: entry index
  core->r[20] = 1u;          // s4: entry count
  core->r[21] = 0x80100000u; // s5: wrapper destination
  core->ram[0x80004u] = 0x00u;
  core->ram[0x80005u] = 0x01u; // current entry offset 0x100
  core->ram[0x80006u] = 0x00u;
  core->ram[0x80007u] = 0x00u;
  core->ram[0x80100u] = 0x02u; // one four-byte back-reference, then terminator
  core->ram[0x80101u] = 0x20u;
  core->ram[0x80102u] = 0x01u;
  core->ram[0x80103u] = 0x00u;
  core->ram[0x4CA9Cu] = 0x40u;
  core->ram[0x4CA9Du] = 0x82u;
  core->ram[0x4CA9Eu] = 0x03u;
  core->ram[0x4CA9Fu] = 0x34u; // authentic `ori v1,zero,0x8240` wrapper bound
  core->r[4] = 0x80080103u;
  core->r[5] = 0x80100000u;
  core->r[6] = 4u;
  core->r[7] = 0x800FFFFFu;
  core->r[9] = 0x80100000u;
  core->r[3] = 0u;
  core->r[31] = 0x8004CA9Cu;
  auto wrapper = tekken3::DecompressorProbe::describe(
      *core, entry, {psx::cpu::ExecutionExitReason::BudgetExhausted, 0x80031C78u, 64u, "cycle budget exhausted"});
  if (!contains(wrapper, "wrapper_entry=0x80080100(RAM+0x080100)") ||
      !contains(wrapper, "entry_index=0/1 source_consumed=3/4 parsed_output=4 expected_output_from_RAM=4/33344") ||
      !contains(wrapper, "scan=complete consistent=1")) {
    std::fprintf(stderr, "decompressor_probe_contract: FAIL — reached wrapper did not resolve its input extent\n");
    return 1;
  }

  core->ram[0x4CA9Fu] = 0u;
  auto wrongInstruction = tekken3::DecompressorProbe::describe(
      *core, entry, {psx::cpu::ExecutionExitReason::BudgetExhausted, 0x80031C78u, 64u, "cycle budget exhausted"});
  if (!contains(wrongInstruction, "wrapper_entry=unresolved") ||
      !contains(wrongInstruction, "limit_instruction=0x00038240 scan=not-run scanned=0")) {
    std::fprintf(stderr, "decompressor_probe_contract: FAIL — wrong wrapper instruction was accepted\n");
    return 1;
  }
  core->ram[0x4CA9Fu] = 0x34u;

  core->ram[0x80004u] = 0xFCu;
  core->ram[0x80005u] = 0xFFu;
  core->ram[0x80006u] = 0x17u;
  core->ram[0x80007u] = 0x00u; // current entry offset 0x17fffc
  for (auto offset = 0x1FFFFCu; offset < 0x200000u; ++offset) {
    core->ram[offset] = 1u;
  }
  core->r[4] = 0x801FFFFDu;
  auto unterminated = tekken3::DecompressorProbe::describe(
      *core, entry, {psx::cpu::ExecutionExitReason::BudgetExhausted, 0x80031C78u, 64u, "cycle budget exhausted"});
  if (!contains(unterminated, "source_consumed=1/4 parsed_output=0 expected_output_from_RAM=unknown/33344") ||
      !contains(unterminated, "scan=missing-terminator-within-mapped-RAM consistent=0")) {
    std::fprintf(stderr, "decompressor_probe_contract: FAIL — unterminated input looked complete\n");
    return 1;
  }

  core->r[16] = 1u;
  auto missingEntry = tekken3::DecompressorProbe::describe(
      *core, entry, {psx::cpu::ExecutionExitReason::BudgetExhausted, 0x80031C78u, 64u, "cycle budget exhausted"});
  if (!contains(missingEntry, "wrapper_entry=unresolved") || contains(missingEntry, "expected_output_from_RAM=4")) {
    std::fprintf(stderr, "decompressor_probe_contract: FAIL — invalid wrapper table reported an entry\n");
    return 1;
  }

  std::printf("decompressor_probe_contract: PASS — 1/1 reached and 1/1 unreached exits, "
              "1/1 valid and 1/1 invalid copy, 1/1 resolved wrapper input, "
              "1/1 wrong wrapper instruction, 1/1 unterminated stream and "
              "1/1 invalid wrapper table classified\n");
  return 0;
}
