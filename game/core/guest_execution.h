#pragma once

#include "execution_exit.h"

#include <cstdint>

class Core;

namespace tekken3::guest {

using NativeFunction = void (*)(Core *);

// A host-owned call may cross display fields without returning from its guest function. The
// original outer return boundary is separate from the guest's live r31 after nested calls.
class BoundedCall {
public:
  bool
  start(Core &core, std::uint32_t address, std::uint32_t returnPc, const char *owner, psx::cpu::ExecutionBudget budget);
  bool resume(Core &core, const char *owner, psx::cpu::ExecutionBudget budget);
  [[nodiscard]] bool pending() const;

private:
  bool accept(Core &core, const psx::cpu::ExecutionResult &result, const char *owner);

  std::uint32_t entry_ = 0;
  std::uint32_t returnPc_ = 0;
  std::uint32_t resumePc_ = 0;
  std::uint32_t suspensions_ = 0;
  bool pending_ = false;
};

void call(Core &core, std::uint32_t address, const char *owner);
void callOriginal(Core &core, std::uint32_t address, const char *owner);
void install(Core &core, std::uint32_t address, const char *name, NativeFunction function);

} // namespace tekken3::guest
