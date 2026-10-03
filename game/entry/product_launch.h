// product_launch.h — the product's one composition: framework devices around this title's runtime.
#pragma once

namespace tekken3 {

class TitleRuntime;

// Compose the framework hardware owners around the authenticated runtime image and run the product.
// `argv[1]`, when present, is the path to the user's USA disc executable.
int launchProduct(TitleRuntime &runtime, int argc, char **argv);

} // namespace tekken3
