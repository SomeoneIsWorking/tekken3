#include "core.h"
#include "game.h"
#include "recomp_iface.h"
#include "tekken3_runtime.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <vector>

void load_exe(const char *path, Core *core);
void interp_coro_run(Core *core, std::uint32_t pc);
void tekken3_cd_response_run(Core *core);
void tekken3_cd_response_dispatch(Core *core, std::uint32_t address);
int tekken3_cd_response_func_index(std::uint32_t address);
std::uint32_t tekken3_cd_response_entry();
std::uint32_t tekken3_cd_response_sentinel();
std::uint32_t tekken3_cd_response_stack();
std::uint32_t tekken3_cd_response_text_start();
std::uint32_t tekken3_cd_response_text_end();
std::uint32_t tekken3_cd_sync_callback();
std::uint32_t tekken3_cd_sync_callback_target();
std::uint32_t tekken3_cd_current_libcd_command();
std::uint32_t tekken3_cd_ack_buffer();
std::uint32_t tekken3_cd_state_command();
std::uint32_t tekken3_cd_published_status();
std::uint32_t tekken3_cd_response_copy();
std::uint32_t tekken3_cd_callback_class();
std::uint32_t tekken3_cd_cd_state();
std::uint32_t tekken3_cd_cd_substate();
std::uint32_t tekken3_cd_cd_init_step();
std::uint32_t tekken3_cd_motor_on_flag();
std::uint32_t tekken3_cd_cd_init_fields();

namespace {

constexpr std::size_t kCpuWords = 34;
constexpr std::size_t kObservedBytes = 38;

struct Returned final {};

void stopAtReturn(Core *, std::uint64_t, std::uint32_t, void *) {
  throw Returned{};
}

struct Observation {
  std::array<std::uint32_t, kCpuWords> cpu{};
  std::array<std::uint8_t, kObservedBytes> bytes{};
  int queueHead = 0;
  int queueTail = 0;
  int responseRead = 0;
  int controllerBank = 0;
};

std::vector<std::uint32_t> observedAddresses() {
  std::vector<std::uint32_t> addresses;
  addresses.reserve(kObservedBytes);
  const auto appendRange = [&addresses](std::uint32_t start, std::uint32_t size) {
    for (std::uint32_t offset = 0; offset < size; ++offset) {
      addresses.push_back(start + offset);
    }
  };
  appendRange(tekken3_cd_ack_buffer(), 8);
  appendRange(tekken3_cd_response_copy(), 8);
  appendRange(tekken3_cd_published_status(), 1);
  appendRange(tekken3_cd_callback_class(), 4);
  appendRange(tekken3_cd_cd_state(), 4);
  appendRange(tekken3_cd_cd_substate(), 4);
  appendRange(tekken3_cd_cd_init_step(), 4);
  appendRange(tekken3_cd_motor_on_flag(), 1);
  appendRange(tekken3_cd_cd_init_fields(), 4);
  return addresses;
}

void seed(Core *core, std::uint8_t response) {
  std::fill_n(core->r, 32, 0);
  core->lo = 0;
  core->hi = 0;
  core->r[29] = tekken3_cd_response_stack();
  core->r[31] = tekken3_cd_response_sentinel();
  for (const std::uint32_t address : observedAddresses()) {
    core->mem_w8(address, 0);
  }
  core->mem_w32(tekken3_cd_sync_callback(), tekken3_cd_sync_callback_target());
  core->mem_w8(tekken3_cd_current_libcd_command(), 1);
  core->mem_w8(tekken3_cd_state_command(), 1);
  core->mem_w32(tekken3_cd_callback_class(), 0x20);
  core->mem_w32(tekken3_cd_cd_state(), 2);
  core->mem_w32(tekken3_cd_cd_substate(), 0x0E);
  core->mem_w32(tekken3_cd_cd_init_step(), 0x16);
  core->mem_w32(tekken3_cd_cd_init_fields(), 1);

  CdcState &cdc = core->game->cdc;
  cdc.index = 1;
  cdc.q_head = 0;
  cdc.q_tail = 1;
  cdc.resp_rd = 0;
  cdc.q[0].type = 3;
  cdc.q[0].len = 1;
  cdc.q[0].resp[0] = response;
}

Observation capture(Core *core) {
  Observation result;
  for (std::size_t index = 0; index < 32; ++index) {
    result.cpu[index] = core->r[index];
  }
  result.cpu[32] = core->lo;
  result.cpu[33] = core->hi;
  std::size_t byte = 0;
  for (const std::uint32_t address : observedAddresses()) {
    result.bytes[byte++] = core->mem_r8(address);
  }
  result.queueHead = core->game->cdc.q_head;
  result.queueTail = core->game->cdc.q_tail;
  result.responseRead = core->game->cdc.resp_rd;
  result.controllerBank = core->game->cdc.index;
  return result;
}

Observation run(const char *executable, bool generated, std::uint8_t response) {
  auto game = std::make_unique<Game>();
  Core *const core = &game->core;
  load_exe(executable, core);
  seed(core, response);
  if (generated) {
    core->use_interp = 0;
    tekken3_cd_response_run(core);
  } else {
    core->use_interp = 1;
    const std::uint32_t sentinel = tekken3_cd_response_sentinel();
    if (!core->pcObserver.arm(&sentinel, 1, stopAtReturn, nullptr)) {
      std::fprintf(stderr, "REFUSED: could not arm CD response return sentinel\n");
      std::exit(2);
    }
    try {
      interp_coro_run(core, tekken3_cd_response_entry());
      std::fprintf(stderr, "FAIL: interpreter returned without reaching CD response sentinel\n");
      std::exit(1);
    } catch (const Returned &) {
    }
    core->pcObserver.disarm();
  }
  return capture(core);
}

bool compare(const Observation &interpreted, const Observation &generated) {
  bool equal = true;
  for (std::size_t index = 0; index < interpreted.cpu.size(); ++index) {
    if (interpreted.cpu[index] != generated.cpu[index]) {
      std::fprintf(stderr,
                   "CPU[%zu] interpreted=0x%08X generated=0x%08X\n",
                   index,
                   interpreted.cpu[index],
                   generated.cpu[index]);
      equal = false;
    }
  }
  for (std::size_t index = 0; index < interpreted.bytes.size(); ++index) {
    if (interpreted.bytes[index] != generated.bytes[index]) {
      std::fprintf(stderr,
                   "RAM[%zu] interpreted=0x%02X generated=0x%02X\n",
                   index,
                   interpreted.bytes[index],
                   generated.bytes[index]);
      equal = false;
    }
  }
  if (interpreted.queueHead != generated.queueHead || interpreted.queueTail != generated.queueTail ||
      interpreted.responseRead != generated.responseRead || interpreted.controllerBank != generated.controllerBank) {
    std::fprintf(stderr,
                 "CDC interpreted=%d/%d/%d/%d generated=%d/%d/%d/%d\n",
                 interpreted.queueHead,
                 interpreted.queueTail,
                 interpreted.responseRead,
                 interpreted.controllerBank,
                 generated.queueHead,
                 generated.queueTail,
                 generated.responseRead,
                 generated.controllerBank);
    equal = false;
  }
  return equal;
}

std::uint8_t observedByte(const Observation &result, std::uint32_t address) {
  const auto addresses = observedAddresses();
  for (std::size_t index = 0; index < addresses.size(); ++index) {
    if (address == addresses[index]) {
      return result.bytes[index];
    }
  }
  return 0xFF;
}

bool expectedPublication(const Observation &result) {
  const bool expected =
      observedByte(result, tekken3_cd_ack_buffer()) == 2 && observedByte(result, tekken3_cd_response_copy()) == 2 &&
      observedByte(result, tekken3_cd_published_status()) == 2 &&
      observedByte(result, tekken3_cd_motor_on_flag()) == 1 &&
      observedByte(result, tekken3_cd_callback_class()) == 0x21 && observedByte(result, tekken3_cd_cd_state()) == 2 &&
      observedByte(result, tekken3_cd_cd_substate()) == 0x0E &&
      observedByte(result, tekken3_cd_cd_init_step()) == 0x17 && result.queueHead == 1 && result.queueTail == 1;
  if (!expected) {
    std::fprintf(stderr, "FAIL: controlled INT3/Getstat did not publish 0x02 and advance init step 0x16 -> 0x17\n");
  }
  return expected;
}

bool rejectsNonMotorStatus(const Observation &result) {
  return observedByte(result, tekken3_cd_ack_buffer()) == 0 && observedByte(result, tekken3_cd_response_copy()) == 0 &&
         observedByte(result, tekken3_cd_published_status()) == 0 &&
         observedByte(result, tekken3_cd_motor_on_flag()) == 0 &&
         observedByte(result, tekken3_cd_callback_class()) == 0x21 &&
         observedByte(result, tekken3_cd_cd_state()) == 2 && observedByte(result, tekken3_cd_cd_substate()) == 0x0E &&
         observedByte(result, tekken3_cd_cd_init_step()) == 0x16;
}

} // namespace

int main(int argc, char **argv) {
  if (argc != 2) {
    std::fprintf(stderr, "usage: %s <PS-X EXE>\n", argv[0]);
    return 2;
  }
  static tekken3::Tekken3Runtime runtime{{tekken3_cd_response_text_start(), tekken3_cd_response_text_end()}};
  static const RecompRegistry recomp = {
      tekken3_cd_response_dispatch,
      tekken3_cd_response_func_index,
      nullptr,
      0,
      nullptr,
      nullptr,
      nullptr,
      nullptr,
  };
  psxport_install_game(runtime);
  psxport_install_recomp(&recomp);

  const Observation interpreted = run(argv[1], false, 2);
  const Observation generated = run(argv[1], true, 2);
  if (!expectedPublication(interpreted) || !expectedPublication(generated) || !compare(interpreted, generated)) {
    return 1;
  }
  const Observation negativeInterpreted = run(argv[1], false, 0);
  const Observation negativeGenerated = run(argv[1], true, 0);
  if (!rejectsNonMotorStatus(negativeInterpreted) || !rejectsNonMotorStatus(negativeGenerated) ||
      !compare(negativeInterpreted, negativeGenerated)) {
    std::fprintf(stderr, "FAIL: non-motor negative control did not retain init step 0x16\n");
    return 1;
  }
  std::printf("PASS CD response boundary: interpreter and shipping recompiler agree 34/34 CPU, "
              "38/38 RAM, and 4/4 CDC fields; INT3/Getstat 0x02 reaches status and advances init "
              "step 0x16 -> 0x17; 0x00 negative control retains step 0x16 in both engines\n");
  return 0;
}
