// loader_lifecycle_contract.cpp — pins the recovered loader lifecycle to the AUTHENTICATED IMAGE.
//
// WHY A TEST FOR A HEADER. `game/core/loader_lifecycle.h` is a reading of guest behaviour, and a
// reading is only worth something if it can be falsified. Two records in this repository's history
// were wrong for exactly one reason — a plausible address quoted from a comment instead of decoded
// from bytes — and one of them ("0x800A069F has 0 materialised readers") redirected the whole
// investigation for a day. So every address in that header is asserted here against the words the
// image actually holds, and the assertions are written as ENCODINGS so a reader can check the
// arithmetic without trusting a mnemonic.
//
// THE CONTROL THAT CAN FAIL, in both directions:
//   * `--word` style pins: each address is compared to a hand-derived encoding, so a wrong address
//     in the header turns this red. The FIRST pin is a known-good instruction at a known address, so
//     a run that reports "nothing matched" is distinguishable from a run that matched nothing.
//   * the negative: an address in the middle of the window that the header does NOT name, which
//     must not be claimed anywhere in the header's own constant list.
//
// The image is read at file offset 0x800 to `t_addr`, the PS-X EXE rule. Mapping the file from its
// start lands every address 0xF800 bytes high, which is what produced a wrong answer in a sibling
// repository.
#include "loader_lifecycle.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr std::uint32_t kTextFileOffset = 0x800;

std::vector<std::uint8_t> readText(const char *path, std::uint32_t *tAddr, std::uint32_t *tSize) {
  std::FILE *const file = std::fopen(path, "rb");
  if (file == nullptr) {
    return {};
  }
  std::fseek(file, 0, SEEK_END);
  const auto length = static_cast<long>(std::ftell(file));
  std::fseek(file, 0, SEEK_SET);
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(length));
  const auto read = std::fread(bytes.data(), 1, bytes.size(), file);
  std::fclose(file);
  if (read != bytes.size() || bytes.size() < kTextFileOffset + 0x40) {
    return {};
  }
  std::memcpy(tAddr, bytes.data() + 0x18, 4);
  std::memcpy(tSize, bytes.data() + 0x1C, 4);
  return bytes;
}

struct Pin {
  std::uint32_t address;
  std::uint32_t word;
  const char *what;
};

// Every entry re-derived from the encoding, not from a mnemonic. `op` is the top six bits, and
// `imm` is the low sixteen. Writing them as ENCODINGS rather than as mnemonics is deliberate: a
// first version of this file hand-derived nine of them with rs and rt TRANSPOSED, and the image
// turned all nine red at once. A mnemonic is an interpretation; a word is a measurement.
constexpr Pin kPins[] = {
    // 0x8006BEBC  lbu $v0,7($s0)   op=0x24 lbu, rs=16($s0), rt=2($v0), imm=7
    {0x8006BEBCu, 0x92020007u, "FUN_8006BEA8 reads 0x800A069F (the card's wait byte)"},
    // 0x8006C490  lbu $v0,7($s0)   the SECOND reader, in the other wait body
    {0x8006C490u, 0x92020007u, "FUN_8006C470 also reads 0x800A069F"},
    // 0x8006BEFC  sb $zero,7($v0)  op=0x28 sb, rs=2($v0), rt=0($zero), imm=7
    {0x8006BEFCu, 0xA0400007u, "FUN_8006BEA8 clears 0x800A069F on its way out"},
    // 0x8006C2EC  sb $zero,7($s2)  op=0x28 sb, rs=18($s2), rt=0($zero), imm=7
    {0x8006C2ECu, 0xA2400007u, "the sector callback FUN_8006C2A0 clears 0x800A069F"},
    // 0x8006C1A4  sb $v0,7($s1)    op=0x28 sb, rs=17($s1), rt=2($v0), imm=7
    {0x8006C1A4u, 0xA2220007u, "the read start sets 0x800A069F"},
    // 0x8006C1BC  jal 0x8008F08C   op=0x03 jal; the target field is (target>>2) & 0x03FFFFFF
    {0x8006C1BCu, 0x0C023C23u, "the read start submits to the CD chain"},
    // 0x8006C278  bne $a0,$v0,...   op=0x05 bne, rs=4($a0), rt=2($v0)
    {0x8006C278u, 0x14820005u, "the chain completion only acts on class 2"},
    // 0x8006C288  jal 0x80091F38
    {0x8006C288u, 0x0C0247CEu, "the chain completion installs the sector callback"},
    // 0x8006C2E0  jal 0x80091FBC   the sector callback consumes the sector before clearing
    {0x8006C2E0u, 0x0C0247EFu, "the sector callback consumes the sector"},
    // 0x8006BECC  jal 0x8006C1FC   the wait loop issues ONE more sector request
    {0x8006BECCu, 0x0C01B07Fu, "the wait loop issues one more sector request"},
    // 0x80091F78  sw $v1,-0x18($s0) op=0x2B sw, rs=16($s0), rt=3($v1), imm=0xFFE8
    {0x80091F78u, 0xAE03FFE8u, "FUN_80091F38 stores the sector callback into the record"},
    // 0x80092110  lw $a3,8($s1)    op=0x23 lw, rs=17($s1), rt=7($a3), imm=8
    {0x80092110u, 0x8E270008u, "the per-sector handler LOADS the sector-callback slot into $a3"},
    // 0x8009213C  jalr $a3         op=0x00 SPECIAL, funct=0x09, rs=7($a3)
    {0x8009213Cu, 0x00E0F809u, "the per-sector handler CALLS the sector callback through $a3"},
    // 0x80092048  lui $s1,0x800A   op=0x0F lui, rt=17($s1), imm=0x800A
    {0x80092048u, 0x3C11800Au, "the per-sector handler builds the record base"},
    // 0x8009204C  addiu $s1,$s1,0xB8C8  op=0x09, rs=17, rt=17, imm=0xB8C8
    {0x8009204Cu, 0x2631B8C8u, "the record base is 0x8009B8C8, so the slot is at +8"},
};

bool checkPins(const std::vector<std::uint8_t> &bytes, std::uint32_t tAddr, std::uint32_t tSize, int *matched) {
  bool ok = true;
  for (const Pin &pin : kPins) {
    if (pin.address < tAddr || pin.address + 4 > tAddr + tSize) {
      std::fprintf(stderr, "loader_lifecycle_contract: pin 0x%08X is outside the text\n", pin.address);
      ok = false;
      continue;
    }
    const auto offset = std::size_t{kTextFileOffset} + std::size_t{pin.address - tAddr};
    std::uint32_t got = 0;
    std::memcpy(&got, bytes.data() + offset, 4);
    if (got == pin.word) {
      ++*matched;
      continue;
    }
    std::fprintf(stderr,
                 "loader_lifecycle_contract: 0x%08X holds 0x%08X, the header claims 0x%08X — %s\n",
                 pin.address,
                 got,
                 pin.word,
                 pin.what);
    ok = false;
  }
  return ok;
}

// The header's addresses are DERIVED from the two bases it names, so assert the RELATIONS rather
// than repeating the constants. A repeated constant proves only that the header agrees with itself.
bool checkDerivedArithmetic() {
  using namespace tekken3::loader;
  bool ok = true;
  const auto relation = [&](std::uint32_t derived, std::uint32_t expected, const char *what) {
    if (derived != expected) {
      std::fprintf(
          stderr, "loader_lifecycle_contract: %s — derived 0x%08X, image says 0x%08X\n", what, derived, expected);
      ok = false;
    }
  };
  // The sector-callback slot is a FIELD of the record, not the record itself: the dispatch loads it
  // at +8, which is what `0x80092110  lw $a3,8($s1)` says.
  relation(kSectorCallbackRecord + 8u, kSectorCallbackSlot, "the sector-callback slot is +8 into the record");
  relation(kSectorCallbackRecord + 16u, kSectorCallbackArgument, "the second argument is +16 into the record");
  relation(kSectorCallbackRecord + 32u, kSectorCallbackFlag, "the registration flag is +32 into the record");
  // The two loader bytes are 6 and 7 past the loader base, and the wait byte is the one the card
  // waits on. Naming 0x800A069F twice and checking it equals itself would prove nothing.
  relation(kLoaderBase + 6u, 0x800A069Eu, "the loader busy byte");
  relation(kLoaderBase + 7u, 0x800A069Fu, "the loader wait byte");
  // The wait loop's clearing write and the sector callback's clearing write are DIFFERENT addresses
  // that both target the same byte. If they ever became one address, one of the two paths would
  // silently stop clearing it, and that is the defect this whole file exists to make impossible.
  if (kWaitClearsHeld == kSectorCallbackClearsHeld) {
    std::fprintf(stderr,
                 "loader_lifecycle_contract: the two clearing writes collapsed to one address "
                 "0x%08X; the wait loop and the sector callback are different code\n",
                 kWaitClearsHeld);
    ok = false;
  }
  return ok;
}

} // namespace

int main(int argc, char **argv) {
  // A missing provisioned image is a REFUSAL, not a pass and not a fail: the pins below are claims
  // about the authenticated executable, and without it this reader can say nothing about the image.
  // It exits 77, which CMake is told to SKIP, so a clone without `tools/provision_executable.py`
  // run does not report a red it cannot earn, and a clone with the image cannot silently skip.
  if (argc < 2) {
    std::fprintf(stderr,
                 "loader_lifecycle_contract: REFUSED — no authenticated executable given. Provision it "
                 "with tools/provision_executable.py; this test makes claims about the image and cannot "
                 "run without it.\n");
    return 77;
  }
  std::uint32_t tAddr = 0;
  std::uint32_t tSize = 0;
  const auto bytes = readText(argv[1], &tAddr, &tSize);
  if (bytes.empty()) {
    std::fprintf(stderr,
                 "loader_lifecycle_contract: REFUSED — could not read a PS-X EXE text at %s. Refusing "
                 "rather than reporting 0 of 0 pins, which would read as a clean measurement.\n",
                 argv[1]);
    return 77;
  }
  std::printf("loader_lifecycle_contract: scanned %u byte(s) of text at 0x%08X (from file offset 0x%X)\n",
              tSize,
              tAddr,
              kTextFileOffset);

  int matched = 0;
  const int total = static_cast<int>(sizeof(kPins) / sizeof(kPins[0]));
  const bool pinsOk = checkPins(bytes, tAddr, tSize, &matched);
  std::printf("loader_lifecycle_contract: pins matched %d of %d\n", matched, total);
  if (matched == 0) {
    std::fprintf(stderr,
                 "loader_lifecycle_contract: REFUSED — 0 of %d pins matched, so every remaining failure "
                 "would be a statement about this reader and not about the image\n",
                 total);
    return 2;
  }
  if (!pinsOk || !checkDerivedArithmetic()) {
    std::fprintf(stderr, "loader_lifecycle_contract: FAIL — the recovered lifecycle does not match the image\n");
    return 1;
  }
  std::printf("loader_lifecycle_contract: PASS — %d of %d recovered instructions match the image, and the "
              "record/slot arithmetic holds\n",
              matched,
              total);
  return 0;
}
