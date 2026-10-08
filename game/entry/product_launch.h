// The product's one composition: framework devices around this title's runtime.
#pragma once

namespace tekken3 {

class TitleRuntime;

// `argv[1]`, when present, is the path to the USA disc executable.
int launchProduct(TitleRuntime &runtime, int argc, char **argv);

} // namespace tekken3
