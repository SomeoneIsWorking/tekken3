#include "tekken3_port.h"
#include "tekken3_program.h"
#include "tekken3_runtime.h"

int main(int argc, char **argv) {
  static tekken3::Tekken3Runtime runtime{{TEKKEN3_RESIDENT_TEXT_LO, TEKKEN3_RESIDENT_TEXT_HI}, TEKKEN3_PROGRAM_ENTRY};
  return tekken3::runPort(runtime, argc, argv);
}
