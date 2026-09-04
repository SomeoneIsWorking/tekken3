#pragma once

#include <cstdint>

class Core;

namespace tekken3::guest {

using NativeFunction = void (*)(Core *);

void call(Core &core, std::uint32_t address, const char *owner);
void callOriginal(Core &core, std::uint32_t address, const char *owner);
void install(Core &core, std::uint32_t address, const char *name, NativeFunction function);

} // namespace tekken3::guest
