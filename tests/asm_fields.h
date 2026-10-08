// Field-level MIPS assembler: fixture guest code is built from fields, not hex literals.

#ifndef TEKKEN3_TEST_ASM_FIELDS_H
#define TEKKEN3_TEST_ASM_FIELDS_H

#include <cstdint>
#include <string>
#include <vector>

namespace tekken3::test::mips {

enum : std::uint32_t {
  kZero = 0,
  kV0 = 2,
  kAt = 1,
  kT0 = 8,
  kT1 = 9,
  kT2 = 10,
  kT3 = 11,
  kS0 = 16,
  kS1 = 17,
  kS2 = 18,
  kRa = 31,
};

constexpr std::uint32_t kOpSpecial = 0x00;
constexpr std::uint32_t kOpJ = 0x02;
constexpr std::uint32_t kOpJal = 0x03;
constexpr std::uint32_t kOpBeq = 0x04;
constexpr std::uint32_t kOpBne = 0x05;
constexpr std::uint32_t kOpAddiu = 0x09;
constexpr std::uint32_t kOpOri = 0x0D;
constexpr std::uint32_t kOpLui = 0x0F;
constexpr std::uint32_t kOpLbu = 0x24;
constexpr std::uint32_t kOpLhu = 0x25;
constexpr std::uint32_t kOpLw = 0x23;
constexpr std::uint32_t kOpSw = 0x2B;
constexpr std::uint32_t kOpSb = 0x28;

constexpr std::uint32_t kFunctJr = 0x08;
constexpr std::uint32_t kFunctJalr = 0x09;
constexpr std::uint32_t kFunctSll = 0x00;

// Held as fields, not mnemonics: different encodings can render as the same mnemonic.
struct Fields {
  std::uint32_t op;
  std::uint32_t rs;
  std::uint32_t rt;
  std::uint32_t imm;
  std::uint32_t funct;
};

constexpr std::uint32_t encode(std::uint32_t op, std::uint32_t rs, std::uint32_t rt, std::uint32_t imm) {
  return (op << 26) | ((rs & 0x1Fu) << 21) | ((rt & 0x1Fu) << 16) | (imm & 0xFFFFu);
}

constexpr std::uint32_t encodeSpecial(std::uint32_t funct, std::uint32_t rs, std::uint32_t rt, std::uint32_t rd) {
  return (funct & 0x3Fu) | ((rs & 0x1Fu) << 21) | ((rt & 0x1Fu) << 16) | ((rd & 0x1Fu) << 11);
}

// Signed 16-bit immediates are rejected, not truncated, when out of range.
constexpr bool fitsSigned16(std::int64_t value) {
  return value >= -32768 && value <= 32767;
}

constexpr std::uint32_t addiu(std::uint32_t rs, std::uint32_t rt, std::int64_t imm) {
  if (!fitsSigned16(imm)) {
    return 0xFFFFFFFFu; // the caller's decoder check reports this as an impossible word
  }
  return encode(kOpAddiu, rs, rt, static_cast<std::uint32_t>(static_cast<std::int16_t>(imm)));
}

constexpr std::uint32_t ori(std::uint32_t rs, std::uint32_t rt, std::uint32_t imm) {
  return encode(kOpOri, rs, rt, imm);
}

constexpr std::uint32_t lui(std::uint32_t rt, std::uint32_t imm) {
  return encode(kOpLui, 0, rt, imm);
}

constexpr std::uint32_t lbu(std::uint32_t rs, std::uint32_t rt, std::int64_t imm) {
  if (!fitsSigned16(imm)) {
    return 0xFFFFFFFFu;
  }
  return encode(kOpLbu, rs, rt, static_cast<std::uint32_t>(static_cast<std::int16_t>(imm)));
}

constexpr std::uint32_t lw(std::uint32_t rs, std::uint32_t rt, std::int64_t imm) {
  if (!fitsSigned16(imm)) {
    return 0xFFFFFFFFu;
  }
  return encode(kOpLw, rs, rt, static_cast<std::uint32_t>(static_cast<std::int16_t>(imm)));
}

constexpr std::uint32_t sw(std::uint32_t rs, std::uint32_t rt, std::int64_t imm) {
  if (!fitsSigned16(imm)) {
    return 0xFFFFFFFFu;
  }
  return encode(kOpSw, rs, rt, static_cast<std::uint32_t>(static_cast<std::int16_t>(imm)));
}

constexpr std::uint32_t sb(std::uint32_t rs, std::uint32_t rt, std::int64_t imm) {
  if (!fitsSigned16(imm)) {
    return 0xFFFFFFFFu;
  }
  return encode(kOpSb, rs, rt, static_cast<std::uint32_t>(static_cast<std::int16_t>(imm)));
}

// Branch fields are word offsets from PC + 4.
constexpr std::uint32_t branchOffset(std::uint32_t pc, std::uint32_t target) {
  return (target - (pc + 4u)) >> 2;
}

constexpr std::uint32_t beq(std::uint32_t rs, std::uint32_t rt, std::uint32_t pc, std::uint32_t target) {
  return encode(kOpBeq, rs, rt, branchOffset(pc, target));
}

constexpr std::uint32_t bne(std::uint32_t rs, std::uint32_t rt, std::uint32_t pc, std::uint32_t target) {
  return encode(kOpBne, rs, rt, branchOffset(pc, target));
}

// `j`/`jal` fields are absolute word indexes; the top nibble comes from the PC's region.
constexpr std::uint32_t j(std::uint32_t pc, std::uint32_t target) {
  (void)pc;
  return (kOpJ << 26) | ((target >> 2) & 0x03FFFFFFu);
}

constexpr std::uint32_t jal(std::uint32_t pc, std::uint32_t target) {
  (void)pc;
  return (kOpJal << 26) | ((target >> 2) & 0x03FFFFFFu);
}

constexpr std::uint32_t jr(std::uint32_t rs) {
  return encodeSpecial(kFunctJr, rs, 0, 0);
}

constexpr std::uint32_t jalr(std::uint32_t rs, std::uint32_t rd) {
  return encodeSpecial(kFunctJalr, rs, 0, rd);
}

constexpr std::uint32_t nop() {
  return encodeSpecial(kFunctSll, 0, 0, 0);
}

// Decoding, for the build -> decode -> compare round trip.
inline Fields decode(std::uint32_t word) {
  Fields fields{};
  fields.op = word >> 26;
  fields.rs = (word >> 21) & 0x1Fu;
  fields.rt = (word >> 16) & 0x1Fu;
  fields.imm = word & 0xFFFFu;
  fields.funct = word & 0x3Fu;
  return fields;
}

inline std::int32_t signedImmediate(std::uint32_t raw) {
  return static_cast<std::int16_t>(static_cast<std::uint16_t>(raw));
}

inline std::uint32_t branchTarget(std::uint32_t word, std::uint32_t pc) {
  return pc + 4u + (static_cast<std::int32_t>(signedImmediate(word & 0xFFFFu)) << 2);
}

inline std::uint32_t jumpTarget(std::uint32_t word, std::uint32_t pc) {
  const std::uint32_t index = word & 0x03FFFFFFu;
  return ((pc + 4u) & 0xF0000000u) | (index << 2);
}

} // namespace tekken3::test::mips

#endif // TEKKEN3_TEST_ASM_FIELDS_H
