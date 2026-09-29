// asm_fields.h — a field-level MIPS assembler, so the fixture's guest program is DERIVED from
// field values instead of transcribed from hex.
//
// WHY THIS EXISTS, and it is not a style preference. `tests/mode_call_budget_resume.cpp` carried a
// 12-word guest body as hex literals. That body was wrong FOUR times before it was right, and a
// fifth time in the diagnostic that found the fourth:
//
//   1. `0x1000FFFF` for `b -7`   — a branch offset is the 16-bit field sign-extended from (PC+4),
//                                   so -7 is 0xFFF9; 0xFFFF is -1, a one-instruction self loop.
//   2. `0x8C2B0698` for `lw $t3,0x698($t1)` — the base register is bits 25..21 and that word
//                                   carries rs=1 ($at), not 9 ($t1). A four slipped in the field.
//   3. `0x1000FFF9` for `b -7`   — op 0x04 is `beq`, and `beq $zero,$zero` IS unconditional, so
//                                   Capstone PRINTS IT AS `b`. A wrong opcode, a correct mnemonic.
//   4. `0x0800FFF9` for `b -7`   — op 0x02 fixed makes it a `j`, whose field is the ABSOLUTE target
//                                   >> 2, not a PC-relative offset. It decoded as `j 0x8003FFE4`,
//                                   into the scratchpad. This is the J-type trap that cost `megamanx4`
//                                   five wrong call targets, all of them plausible addresses.
//   5. `0x272A0698` for `addiu $t1,$t1,0x698` and `0xAC220000` for `sw $v0,0($t1)` — the register
//                                   fields again, both caught by the field check the moment it ran.
//
// Every one of those produced a word that DISASSEMBLED to a plausible mnemonic, so no amount of
// reading the rendered text could have caught any of them. That is the whole argument for building
// the program from fields: the error class is a transcription error, and the cure is to remove the
// transcription, not to proofread it harder.
//
// So each instruction below is a FUNCTION OF ITS FIELDS, and the words in the program are the
// function's return value. A mistake becomes impossible to express rather than merely unlikely.
// The decoder in the test then reads the fields back out of the built words and compares them with
// the fields that were requested, which is a round trip: build -> decode -> compare.

#ifndef TEKKEN3_TEST_ASM_FIELDS_H
#define TEKKEN3_TEST_ASM_FIELDS_H

#include <cstdint>
#include <string>
#include <vector>

namespace tekken3::test::mips {

// MIPS register numbers, named so a call site cannot silently pass the wrong one.
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

// One decoded instruction, held as FIELDS. There is deliberately no mnemonic string anywhere in
// this header: a mnemonic is an interpretation, and two different encodings share one
// (`beq $zero,$zero` and `b` both render as a branch; `j 0x8004FA68` and `jr $t0` can both land on
// the same address). Fields cannot alias.
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

// `addiu`/`ori`/`andi`/`xori` take a SIGN-EXTENDED 16-bit immediate. Wrapping a value that does not
// fit is exactly the bug the operator named: a large unsigned displacement silently becomes a
// negative one, and the guest then reads and writes inside its own code. So this REJECTS rather than
// truncates, which is the difference between a loud failure and a plausible wrong address.
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

// A BRANCH field is a PC-RELATIVE word offset from (PC + 4). This is the quantity that is not the
// target address, and reading it as one is error 1 above.
constexpr std::uint32_t branchOffset(std::uint32_t pc, std::uint32_t target) {
  return (target - (pc + 4u)) >> 2;
}

constexpr std::uint32_t beq(std::uint32_t rs, std::uint32_t rt, std::uint32_t pc, std::uint32_t target) {
  return encode(kOpBeq, rs, rt, branchOffset(pc, target));
}

constexpr std::uint32_t bne(std::uint32_t rs, std::uint32_t rt, std::uint32_t pc, std::uint32_t target) {
  return encode(kOpBne, rs, rt, branchOffset(pc, target));
}

// A `j`/`jal` field is the ABSOLUTE index of the target in units of 4, with the top nibble coming
// from the PC's own region at execution time. This is the quantity that is NOT a PC-relative
// offset, and reading it as one is error 4 above — the trap that cost megamanx4 five plausible
// addresses. `pc` is taken so the caller cannot pass an index by mistake without it being obvious.
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

// --- the other direction, used to prove the round trip ------------------------
//
// `decode` reads the FIELDS back out. `branchTarget` and `jumpTarget` are the two that matter, and
// they take the instruction's own PC because a branch field and a jump field mean different things
// and the difference is the whole of error 4.
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
