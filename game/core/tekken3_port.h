#pragma once

namespace tekken3 {

class Tekken3Runtime;

// Compose the framework hardware owners around the authenticated runtime image and run it.
int runPort(Tekken3Runtime &runtime, int argc, char **argv);

} // namespace tekken3
