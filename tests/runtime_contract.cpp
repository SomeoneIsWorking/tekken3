#include "game_iface.h"
#include "tekken3_runtime.h"

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <type_traits>

namespace {

static_assert(std::is_base_of_v<GameRuntime, tekken3::Tekken3Runtime>);
static_assert(!std::is_base_of_v<LegacyGameRuntimeAdapter, tekken3::Tekken3Runtime>);

std::string readSource(const std::filesystem::path &path) {
  std::ifstream input(path);
  std::ostringstream contents;
  if (input) {
    contents << input.rdbuf();
  }
  return contents.str();
}

bool rejectsAdapterVocabulary(const std::filesystem::path &path) {
  const std::string source = readSource(path);
  if (source.empty()) {
    return false;
  }
  const char *forbidden[] = {
      "LegacyGameRuntimeAdapter",
      "GameConfig",
      "GameHooks",
      "game_iface.h",
      "legacy_game_config.h",
      "legacy_game_hooks.h",
  };
  for (const char *token : forbidden) {
    if (source.find(token) != std::string::npos) {
      return false;
    }
  }
  return true;
}

} // namespace

int main() {
  const std::filesystem::path root = std::filesystem::path(__FILE__).parent_path().parent_path();
  if (!rejectsAdapterVocabulary(root / "game/core/tekken3_runtime.h") ||
      !rejectsAdapterVocabulary(root / "game/core/tekken3_runtime.cpp")) {
    std::fprintf(stderr, "runtime_contract: FAIL — runtime source regained adapter/config/hooks vocabulary\n");
    return 1;
  }
  std::printf("runtime_contract: PASS — direct GameRuntime inheritance and 6/6 adapter tokens absent\n");
  return 0;
}
