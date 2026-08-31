#include "recomp_register.h"
#include "tekken3_port.h"
#include "tekken3_program.h"
#include "tekken3_runtime.h"

#include <cstdio>
#include <cstring>

int main(int argc, char **argv) {
  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "-h") == 0 || std::strcmp(argv[index], "--help") == 0) {
      std::printf("usage: tekken3_port [disc]\n\n"
                  "Run the Tekken 3 port with an optional path to the user's USA disc image.\n");
      return 0;
    }
  }
  static tekken3::Tekken3Runtime runtime{{TEKKEN3_RESIDENT_TEXT_LO, TEKKEN3_RESIDENT_TEXT_HI},
                                         TEKKEN3_PROGRAM_ENTRY,
                                         tekken3::recompiledProgramBindings()};
  return tekken3::runPort(runtime, argc, argv);
}
