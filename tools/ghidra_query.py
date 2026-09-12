#!/usr/bin/env python3
"""Query the authenticated Tekken 3 text imported into build/ghidra/tekken3 with PyGhidra.

WHY THIS EXISTS. A byte scan cannot establish whether a Tekken loader address is a function,
data reference, or delay-slot side effect. Ghidra's reference model reports these distinctions
and counts the code and data it scanned.

Usage:
    tools/ghidra_query.py xrefs 0x80052CC4    every reference TO addr, with type + owning function
    tools/ghidra_query.py func  0x80052CC4    containing function + decompiled C
    tools/ghidra_query.py calls 0x80052CC4    what that function calls
    tools/ghidra_query.py data  0x8009B750 16 dump N words with symbol/xref annotation
    tools/ghidra_query.py disasm 0x80052CC4 0x80052D20
                                                exact instructions in [start, end)
    tools/ghidra_query.py scan  ctc2            every instruction whose mnemonic matches, with
                                                operands + owning function + the enclosing function's
                                                full instruction list

`scan` exists because some leaves are identified by the INSTRUCTION they execute rather than by a
name, a string or a caller — libgte's SetGeomOffset/SetGeomScreen are `ctc2` into cop2 control
registers 24/25/26 and nothing else in the image marks them. It reports the DENOMINATOR (instructions
walked, functions defined) on every run, so "0 matches" is distinguishable from "I never looked", and
it is blind to any site Ghidra did not disassemble as code — which it also counts and prints.

The project contains no shipped game data. Import the verified text bytes from the user's
provisioned executable at load address 0x80010000 into build/ghidra/tekken3 as text.bin.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.join(ROOT, "build", "ghidra")
NAME = "tekken3"
PROGRAM = "/text.bin"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    mode, addr_s = sys.argv[1], sys.argv[2]

    import pyghidra
    pyghidra.start()
    from ghidra.app.decompiler import DecompInterface
    from ghidra.util.task import ConsoleTaskMonitor

    # Open the program ALREADY IN THE PROJECT. The older open_program(path, ...) call silently
    # created a fresh, empty program instead — which is why every query returned zero and memory
    # reads threw: there was nothing in it. open_project + program_context binds the saved one.
    project = pyghidra.open_project(PROJ, NAME)
    with pyghidra.program_context(project, PROGRAM) as prog:
        af = prog.getAddressFactory()
        fm = prog.getFunctionManager()
        addr = af.getAddress(addr_s)
        if mode != "scan" and addr is None:
            print(f"invalid address: {addr_s}")
            return 2

        def owner_str(a):
            f = fm.getFunctionContaining(a)
            return "%s @%s" % (f.getName(), f.getEntryPoint()) if f else "(not in a function)"

        if mode == "xrefs":
            refs = list(prog.getReferenceManager().getReferencesTo(addr))
            calls = 0
            for r in refs:
                t = r.getReferenceType().getName()
                if "CALL" in t:
                    calls += 1
                print("  %s  %-16s from %s" % (r.getFromAddress(), t, owner_str(r.getFromAddress())))
            print("total %d reference(s) to %s  (%d call, %d other)" % (len(refs), addr, calls,
                                                                        len(refs) - calls))
            if refs and calls == 0:
                print("  NOTE: zero CALL references but %d other(s) — this is reached INDIRECTLY "
                      "(installed into a table / called through a pointer), not dead code." % len(refs))

        elif mode == "func":
            # Accepts MANY addresses in one invocation. Ghidra/PyGhidra start-up dominates the cost
            # of a single query (tens of seconds), so decompiling a subsystem one function per
            # process was paying that toll a dozen times over. Every address given is decompiled
            # into the same output; unresolvable ones are reported and counted, never skipped
            # silently, so a run that decompiles nothing says so and exits non-zero.
            di = DecompInterface()
            di.openProgram(prog)
            ok = miss = 0
            for addr_arg in sys.argv[2:]:
                a = af.getAddress(addr_arg)
                f = fm.getFunctionContaining(a)
                if f is None:
                    print("// no function contains %s (data, or not yet defined)" % addr_arg)
                    miss += 1
                    continue
                print("// %s  entry=%s  body=%s" % (f.getName(), f.getEntryPoint(), f.getBody()))
                res = di.decompileFunction(f, 120, ConsoleTaskMonitor())
                print(res.getDecompiledFunction().getC() if res.decompileCompleted()
                      else "// decompilation failed: %s" % res.getErrorMessage())
                ok += 1
            print("// decompiled %d of %d requested address(es), %d unresolved"
                  % (ok, ok + miss, miss))
            if ok == 0:
                return 1

        elif mode == "calls":
            f = fm.getFunctionContaining(addr)
            if f is None:
                print("no function contains %s" % addr)
                return 1
            for c in sorted(f.getCalledFunctions(ConsoleTaskMonitor()), key=lambda x: str(x.getEntryPoint())):
                print("  %s  %s" % (c.getEntryPoint(), c.getName()))

        elif mode == "data":
            n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
            mem = prog.getMemory()
            for i in range(n):
                a = addr.add(i * 4)
                v = mem.getInt(a) & 0xFFFFFFFF
                tgt = af.getAddress("0x%08X" % v) if 0x80000000 <= v < 0x80200000 else None
                note = ""
                if tgt is not None:
                    fn = fm.getFunctionContaining(tgt)
                    if fn is not None:
                        note = "  -> %s @%s" % (fn.getName(), fn.getEntryPoint())
                print("  %s  %08X%s" % (a, v, note))
        elif mode == "disasm":
            if len(sys.argv) != 4:
                print("disasm requires start and exclusive end addresses")
                return 2
            end = af.getAddress(sys.argv[3])
            if end is None:
                print(f"invalid exclusive end address: {sys.argv[3]}")
                return 2
            if addr.compareTo(end) >= 0:
                print("disasm end must be greater than start")
                return 2
            listing = prog.getListing()
            hits = []
            for ins in listing.getInstructions(addr, True):
                if ins.getAddress().compareTo(end) >= 0:
                    break
                hits.append(ins)
                print("  {}  {:<8} {}".format(
                    ins.getAddress(), ins.getMnemonicString(),
                    ", ".join(str(ins.getDefaultOperandRepresentation(i))
                              for i in range(ins.getNumOperands()))))
            print(f"// disassembled {len(hits)} instruction(s) in [{addr}, {end}); "
                  f"requested {end.subtract(addr)} byte(s)")
            if not hits:
                print("// REFUSED: Ghidra has no disassembled instructions in the requested range")
                return 1
        elif mode == "scan":
            # `addr_s` is a mnemonic prefix here, not an address.
            want = addr_s.lower()
            listing = prog.getListing()
            total = 0
            hits = []
            for ins in listing.getInstructions(True):
                total += 1
                if ins.getMnemonicString().lower().startswith(want):
                    hits.append(ins)
            # DENOMINATOR, always: a scan that matched nothing must still say what it walked and
            # what it structurally cannot see, or "(none)" reads as an answer.
            nfunc = fm.getFunctionCount()
            defined = sum(1 for _ in listing.getInstructions(True))
            mem_bytes = sum(int(b.getSize()) for b in prog.getMemory().getBlocks())
            print("// scanned %d disassembled instruction(s) across %d defined function(s) in %d "
                  "byte(s) of memory, looking for mnemonic prefix '%s'"
                  % (total, nfunc, mem_bytes, want))
            print("// BLIND SPOT: bytes Ghidra never disassembled as code are invisible to this "
                  "scan — %d of %d bytes are covered by instructions (%.1f%%)"
                  % (defined * 4, mem_bytes, 100.0 * defined * 4 / mem_bytes if mem_bytes else 0.0))
            for ins in hits:
                a = ins.getAddress()
                print("  %s  %-8s %s   [%s]"
                      % (a, ins.getMnemonicString(),
                         ", ".join(str(ins.getDefaultOperandRepresentation(i))
                                   for i in range(ins.getNumOperands())),
                         owner_str(a)))
            print("// %d match(es)" % len(hits))
            # The enclosing function of each hit, disassembled in full — a leaf identified by one
            # instruction is only understood with its whole body in view.
            seen = set()
            for ins in hits:
                f = fm.getFunctionContaining(ins.getAddress())
                if f is None or str(f.getEntryPoint()) in seen:
                    continue
                seen.add(str(f.getEntryPoint()))
                print("\n// ---- %s  entry=%s  body=%s" % (f.getName(), f.getEntryPoint(), f.getBody()))
                for bi in listing.getInstructions(f.getBody(), True):
                    print("  %s  %-8s %s" % (bi.getAddress(), bi.getMnemonicString(),
                                             ", ".join(str(bi.getDefaultOperandRepresentation(i))
                                                       for i in range(bi.getNumOperands()))))
            if not hits:
                return 1

        else:
            print(__doc__)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
