#include "entry/product_launch.h"
#include "program/program_facts.h"
#include "program/title_runtime.h"

#include <cstdio>
#include <cstring>

namespace {

constexpr const char *kUsage = "usage: tekken3_port [disc]\n\n"
                               "Run the Tekken 3 port with an optional path to the user's USA disc image.\n";

bool asksForHelp(int argc, char **argv) {
  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "-h") == 0 || std::strcmp(argv[index], "--help") == 0) {
      return true;
    }
  }
  return false;
}

} // namespace

int main(int argc, char **argv) {
  if (asksForHelp(argc, argv)) {
    std::fputs(kUsage, stdout);
    return 0;
  }
  tekken3::TitleRuntime runtime{{tekken3::program::kResidentPhysicalLo, tekken3::program::kResidentPhysicalHi},
                                tekken3::program::kEntry};
  return tekken3::launchProduct(runtime, argc, argv);
}
