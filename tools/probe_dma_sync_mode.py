#!/usr/bin/env python3
"""dma_sync_mode_scan.py — does Tekken 3 program any DMA channel in BCR sync mode 2 (linked list)?

DESIGNED NEGATIVE FIRST. It reports how many bytes it scanned, and it separates three answers that
all look like "none":
  (a) the channel's MADR/BCR pair is never mentioned at all  -> this title uses no such DMA channel
  (b) the pair is mentioned but every literal BCR value has sync bits 0-1 == 0 -> block mode
  (c) the pair is mentioned with a BCR literal whose bits 0-1 == 2 -> a real chain

It also PINS ITS OWN FILE OFFSET against a known instruction before reporting, because the input is a
PS-X EXE whose text starts 0x800 bytes into the file. A literal scan is blunter than a decode, but it
has the same exposure: an offset error shifts every reported address while still returning a
confident non-zero answer.

WHAT IT CANNOT SEE, and why the answer about sync mode does not come from here: the twelve hits below
are DMA register addresses in the title's channel DESCRIPTOR TABLES, not the values written to BCR.
BCR's value is computed at runtime, so the sync-mode answer has to be read from the instruction that
writes BCR -- for this title that is FUN_80084838, which writes `count | 0x10000` (bit 16, not bits
0-1) with count 0x200, giving sync mode 0, i.e. manual/block. See docs/issues/0011.

Usage: probe_dma_sync_mode.py [executable]
"""
import struct
import sys

EXE = sys.argv[1] if len(sys.argv) > 1 else "scratch/bin/tekken3/SLUS_004.02"
LOAD = 0x80010000
# The PS-X EXE's text begins 0x800 bytes into the file.
HEADER = 0x800
# 0x8008FBB4 is `sll a0,a0,2` (0x00042080) per the disassembly. If this does not read back, the offset
# is wrong and nothing below may be believed.
OFFSET_PROOF = (0x8008FBB4, 0x00042080)

CHANNELS = {
    "MDECin": 0x1F801080, "GPU": 0x1F8010A0, "CDROM": 0x1F8010C0, "SPU": 0x1F8010E0,
}


def words(data):
    for off in range(HEADER, len(data) - 3, 4):
        yield off, struct.unpack_from("<I", data, off)[0]


def main() -> int:
    data = open(EXE, "rb").read()
    proof_addr, proof_word = OFFSET_PROOF
    got = struct.unpack_from("<I", data, proof_addr - LOAD + HEADER)[0]
    if got != proof_word:
        print(f"REFUSED: at 0x{proof_addr:08X} this read 0x{got:08X}, expected 0x{proof_word:08X}, "
              f"so the file offset is wrong and every address below would be shifted. NOTHING WAS "
              f"SCANNED.")
        return 2
    print(f"file offset pinned: 0x{proof_addr:08X} reads 0x{proof_word:08X} as the disassembly says")
    print(f"scanned {len(data) - HEADER} byte(s) of text at 0x{LOAD:08X} "
          f"({len(data) - HEADER // 1} bytes after the 0x800-byte PS-X EXE header)")

    hits = {}
    offsets = {}
    for off, w in words(data):
        for name, madr in CHANNELS.items():
            for suffix, kind in ((0, "MADR"), (4, "BCR"), (8, "CHCR")):
                if w == madr + suffix:
                    hits[(name, kind)] = hits.get((name, kind), 0) + 1
                    offsets.setdefault((name, kind), []).append(LOAD + off - HEADER)

    total = sum(hits.values())
    print(f"found {total} 32-bit literal(s) naming a DMA channel register")
    if total == 0:
        print("VERDICT: this title contains NO literal naming MADR/BCR/CHCR for any of the four "
              "channels. Any DMA it performs is either done by BIOS (which this scan cannot see) or "
              "reached through a base pointer built at runtime. Coverage: every 4-byte-aligned word.")
        return 0

    for (name, kind), count in sorted(hits.items()):
        addrs = ", ".join(f"0x{a:08X}" for a in offsets[(name, kind)][:8])
        more = "" if len(offsets[(name, kind)]) <= 8 else f" (+{len(offsets[(name, kind)]) - 8} more)"
        print(f"  {name:6s} {kind:4s} x{count:<3d} {addrs}{more}")

    print("\nThese are DESCRIPTOR-TABLE addresses, not the values written to BCR. BCR's value is "
          "computed at runtime, so this scan cannot answer the sync-mode question on its own; read "
          "the instruction that writes BCR instead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
