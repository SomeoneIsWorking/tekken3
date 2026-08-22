#include "state.h"

extern "C" {
#include "irq.h"
}

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

bool irqLineAsserted = false;

struct InterruptSnapshot {
  std::uint32_t status;
  std::uint32_t mask;
};

InterruptSnapshot snapshot() {
  return {
      IRQ_Read(0x1F801070u) & 0x7FFu,
      IRQ_Read(0x1F801074u) & 0x7FFu,
  };
}

bool expect(const char *label, const InterruptSnapshot actual, const InterruptSnapshot expected) {
  if (actual.status == expected.status && actual.mask == expected.mask) {
    return true;
  }
  std::fprintf(stderr,
               "irq_oracle: FAIL %s status=0x%03X/mask=0x%03X, expected "
               "status=0x%03X/mask=0x%03X\n",
               label,
               actual.status,
               actual.mask,
               expected.status,
               expected.mask);
  return false;
}

} // namespace

extern "C" void CPU_AssertIRQ(unsigned, bool asserted) {
  irqLineAsserted = asserted;
}

extern "C" int MDFNSS_StateAction(void *, int, int, SFORMAT *, const char *) {
  return 1;
}

int main(int argc, char **argv) {
  if (argc > 2 || (argc == 2 && std::strcmp(argv[1], "--selftest") != 0)) {
    std::fprintf(stderr, "usage: %s [--selftest]\n", argv[0]);
    return 2;
  }

  IRQ_Power();
  if (!expect("power-on", snapshot(), {0u, 0u}) || irqLineAsserted) {
    return 1;
  }

  if (argc == 2) {
    // Positive opposite-answer fixture: the same vendored controller must also expose a non-zero
    // status/mask and assert the CPU line. This keeps the all-zero Tekken reset result from being
    // accepted merely because the instrument can only report zeros.
    IRQ_Assert(IRQ_CD, true);
    IRQ_Write(0x1F801074u, 4u);
    if (!expect("asserted CD interrupt", snapshot(), {4u, 4u}) || !irqLineAsserted) {
      return 1;
    }
  }

  // FUN_80085d5c performs this exact device sequence at 0x80085D94..0x80085DA0:
  // write zero to I_MASK, read it back, then write that value to I_STAT. The addresses and operand
  // flow are checked against the selected executable by tools/recomp_boundary.py; this executable
  // supplies the independent Mednafen IRQ semantics for those accesses.
  IRQ_Write(0x1F801074u, 0u);
  const std::uint32_t maskReadback = IRQ_Read(0x1F801074u) & 0xFFFFu;
  IRQ_Write(0x1F801070u, maskReadback);
  const InterruptSnapshot final = snapshot();
  if (!expect("Tekken interrupt reset", final, {0u, 0u}) || irqLineAsserted) {
    return 1;
  }

  std::printf("# IRQ-ORACLE mask-readback=0x%04X status=0x%03X mask=0x%03X line=%u\n",
              maskReadback,
              final.status,
              final.mask,
              irqLineAsserted ? 1u : 0u);
  if (argc == 2) {
    std::printf("irq_oracle: SELFTEST 2/2 — non-zero assertion and Tekken reset both observed\n");
  }
  return 0;
}
