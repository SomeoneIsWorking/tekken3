#pragma once

#include "recompiled_program_bindings.h"

namespace tekken3 {

// Install the generated resident substrate behind psxport's game-independent registry seam.
void installRecompiledProgram();
const RecompiledProgramBindings &recompiledProgramBindings();

} // namespace tekken3
