#!/usr/bin/env python3
"""Build Tekken 3's 4:3-versus-16:9 widescreen picture pair from the real product.

WHY A TOOL AND NOT TWO COMMANDS. `PSXPORT_PRESENT_SINK` and the settings file are process-wide, so
each aspect must be captured in its OWN process. `ASPECT_AUTO` (`aspect=3`) resolves against the
SINK's aspect, so a headless run of it measures 4:3 while appearing to be wide — which is why nothing
here reads a config value as evidence. Each leg names its own tracked `.ini` through
`PSXPORT_SETTINGS`, and the witness quoted is the product's own `render_width` / `native_width` pair,
never `wide_engine`.

SCOPE. Tekken 3 (`SLUS_004.02`) is already 60 fps, so this tool measures WIDESCREEN AND NOTHING ELSE.
Both tracked settings pin `fps60=0`, and no interpolation, lerp or temporal pipeline is enabled,
requested or implied anywhere here. If a run ever reports an fps60 row as active on this title, that
is a defect to report, not a setting to use.

THE `[wide]` LINE HAS TO BE READ TWICE. `picture_announce` prints on CHANGE, and the title's own
display publication happens AFTER the first announce, so a boot log carries a pre-publication width
first and the steady state later. This tool records EVERY `[wide]` line in order and reports all of
them, so a reader can see which one was quoted.

GUEST-RESOLUTION READBACK, NOT THE SINK. `shot` is the guest's own presented draw region, which is
what the shared reporter needs; the headless sink is a different size per aspect so two sink images
are not comparable at one scale. The sink is still pinned per leg so an accidental AUTO leg could not
resolve to the wrong shape.

The tool launches the product itself, refuses to start while another product binary holds the
machine's single slot, and kills only PIDs it captured. Never `pkill`/`pgrep -f`.

    tools/probe_tekken3_widescreen_pair.py --selftest
    tools/probe_tekken3_widescreen_pair.py --disc "$DISC" --frame 1200

`--disc`, or `$PSXPORT_DISC`, names the user's image. There is no default: a machine-specific path
baked into a tracked tool is exactly what must never ship, and a default is that path with extra
steps. The tool refuses by name and says which variable to set.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / "external" / "psxport"
SCRATCH = ROOT / "scratch" / "wproof"
# The user's disc image is RUNTIME INPUT and is named by the environment, never baked into a tracked
# file: a machine-specific absolute path in a tracked tool is the one thing that must never ship, and
# the product takes the same variable. No default, because a default is a machine path with extra
# steps — the tool refuses by name instead and says which variable to set.
DISC_ENV = "PSXPORT_DISC"

sys.path.insert(0, str(FRAMEWORK / "tools"))
sys.path.insert(0, str(FRAMEWORK / "tools" / "port"))

# The measured Tekken view extent, used ONLY to size the sink. The title's 368-pixel GP1 display mode
# is decoded generically by the framework and bound to the shared projection plan by
# `tekken3::widescreen::WidescreenProjection`, whose hermetic contract covers the wide 384 -> 512 projection, so the evidence
# quoted below is the product's own render_width and never this constant.
NATIVE_WIDTH = 384
SINK_HEIGHT = 720

LEG_SETTINGS = {"4x3": "config/aspect_4x3.ini", "16x9": "config/aspect_16x9.ini"}
ASPECT_VALUES = {"4x3": 0, "16x9": 1}

# The keys `Mods::load` actually accepts, from `runtime/psx/mods.cpp`. It has NO comment support: it
# splits every line on the first `=` and compares the whole prefix as the key, so a documented settings
# file emits `unknown key "# ..." ignored — it configures nothing` for every comment line that happens
# to contain an `=`. This list is here so the selftest can assert the tracked files parse CLEANLY
# rather than asserting a comment convention the parser does not share.
SETTINGS_KEYS = frozenset({
    "aspect", "ires", "ires_auto", "face_order", "ssao", "light", "shadows",
    "shadow_strength", "fps60", "ssao_strength", "ssao_radius", "ssao_bias", "ssao_range",
    "light_dir", "light_ambient", "light_diffuse",
})

PRODUCT = re.compile(r"^.*/([A-Za-z0-9_.]*_port)$")
WIDE_LINE = re.compile(r"native picture: aspect=(\d+) wide_engine=(\d+) "
                       r"native_width=(\d+) render_width=(\d+)")
SHOT_LINE = re.compile(r"\[gpu_shot\] wrote (\S+) \((\d+)x(\d+)")
PRESENT_SHOT_LINE = re.compile(
    r"present_shot.*wrote (\S+) \((\d+)x(\d+).*non-black (\d+)/(\d+) \(([\d.]+)%\)")
# The DETECTOR deliberately has no leading `\b`. The product's own config audit prints the knob as
# `PSXPORT_FPS60`, and `_` is a word character, so `\bfps60\b` cannot match inside it — the pattern
# silently missed every line the product uses most, which is the shape a real run produces. A
# detector that cannot match the string it exists to match reports a clean run, so the selftest feeds
# it the real `[cfg] PSXPORT_FPS60 = ...` line.
FPS60_ROW = re.compile(r"fps60", re.IGNORECASE)


def other_product_running() -> str | None:
    """A running product, matched on the EXECUTABLE, never anywhere in the command line.

    Matching anywhere is wrong: a shell that merely mentions `tekken3_port` in an argument is not a
    running product, and refusing on it would report a busy machine that is idle.
    """
    for line in subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True,
                               check=False).stdout.splitlines()[1:]:
        _, _, args = line.strip().partition(" ")
        executable = args.split(" ", 1)[0]
        if PRODUCT.match(executable) and "tekken3_port" not in executable:
            return line.strip()
    return None


def sink_width(aspect: int) -> int:
    return NATIVE_WIDTH if aspect == 0 else NATIVE_WIDTH * 16 // 12


def parse_wide_lines(log_text: str) -> list[dict]:
    """EVERY `[wide] native picture:` line, in order, with the source line it came from.

    A short answer has to declare itself: this returns every occurrence it found and the caller
    reports the count, because the FIRST one is not the steady state and reporting only that would be
    publishing a pre-publication value as the result.
    """
    found = []
    for number, line in enumerate(log_text.splitlines(), start=1):
        found_match = WIDE_LINE.search(line)
        if found_match:
            found.append({
                "log_line": number,
                "aspect": int(found_match.group(1)),
                "wide_engine": int(found_match.group(2)),
                "native_width": int(found_match.group(3)),
                "render_width": int(found_match.group(4)),
                "text": line.split("] ", 1)[-1],
            })
    return found


def classify_wide(lines: list[dict]) -> dict:
    """Which `[wide]` line is the steady state, and did the product actually widen.

    The LAST line is the post-latch steady state, because `picture_announce` prints only on CHANGE and
    the title's own display publication is what changes it. `widened` is `render_width >
    native_width` on THAT line, and nothing else.
    """
    if not lines:
        return {"widened": None,
                "reason": "the product printed NO [wide] native picture line at all, so it never "
                          "announced a picture and there is nothing to read"}
    last = lines[-1]
    return {
        "steady_state_log_line": last["log_line"],
        "native_width": last["native_width"],
        "render_width": last["render_width"],
        "widened": last["render_width"] > last["native_width"],
        "announced": len(lines),
    }


def parse_telemetry(text: str) -> dict:
    """Guest-execution counters out of the debug endpoint's own `guest` reply.

    This is the SIMULATION-UNDISTURBED witness: the picture may change and these numbers must not.
    Every counter rides through verbatim, including the fallback ones, so a fallback that did not
    happen is visible as 0 rather than absent.
    """
    counters = {key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", text)}
    if not counters:
        raise ValueError(f"the guest reply carried no counters: {text.strip()!r}")
    return counters


def find_fps60_activity(log_text: str) -> list[dict]:
    """Every log line that mentions an fps60 knob, CLASSIFIED as active or a bare mention.

    This title is 60 fps already and takes no interpolation path, so an fps60 knob reported as ON is a
    defect. The classification is not decoration: `Mods::load` has no comment support, so a documented
    settings file produces `unknown key "# fps60" ignored` on every run — and a check that simply
    counted the word `fps60` would report that as an out-of-scope enhancement being enabled, which is
    the opposite of what the line says.

    Three shapes, each read for what it means rather than for the presence of the word:

      `fps60` followed by a VALUE  — `1`/`true` is ON, `0`/`false` is off. The config audit prints
        booleans as `false`, so requiring a digit would have called `[cfg] PSXPORT_FPS60 = false` a
        non-match and `[cfg] PSXPORT_FPS60 = true` a match by accident of the pattern, not the reading.
      `fps60` followed by a selection state — `(selected)`, `(on)`, `enabled` — is ON.
      `unknown key ...` — a COMMENT the parser could not read, never ON, whatever it names.
    """
    selection = re.compile(r"fps60\b[^\n]*\((?:selected|on|enabled)\)", re.IGNORECASE)
    value = re.compile(r"fps60\b[^\n=]*=\s*([01]|true|false)\b", re.IGNORECASE)
    found = []
    for line in log_text.splitlines():
        if not FPS60_ROW.search(line):
            continue
        if "unknown key" in line:
            active = False
        elif selection.search(line):
            active = True
        else:
            found_value = value.search(line)
            # No readable value and no selection state: the word is present but nothing was decided
            # here, so it is a mention. Deciding it ON would be a guess.
            active = bool(found_value and found_value.group(1).lower() in ("1", "true"))
        found.append({"active": active, "text": line.strip()})
    return found


def run_leg(leg: str, frame: int, port: int, binary: pathlib.Path, timeout: int,
            disc: str) -> dict:
    settings = ROOT / LEG_SETTINGS[leg]
    if not settings.is_file():
        raise SystemExit(f"REFUSED: tracked settings {settings} is missing; the product would run on "
                         f"whatever untracked ini sits beside it. NOTHING WAS MEASURED.")
    aspect = ASPECT_VALUES[leg]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    log = SCRATCH / f"leg_{leg}.log"
    capture = SCRATCH / "shots" / f"{leg}-f{frame}.ppm"
    capture.parent.mkdir(parents=True, exist_ok=True)

    from launch_environment import agent_environment

    busy = other_product_running()
    if busy:
        raise SystemExit(f"REFUSED: another product is already running ({busy}); the machine has one "
                         f"product slot. NOTHING WAS MEASURED.")

    environment = agent_environment(os.environ, settings=settings)
    environment.update({
        "PSXPORT_PRESENT_SINK": f"{sink_width(aspect)}x{SINK_HEIGHT}",
        "PSXPORT_LOG_FILE": str(log),
        "PSXPORT_DISC": disc,
        "PSXPORT_DEBUG_SERVER": str(port),
        "PSXPORT_WATCHDOG": "900",
        "PSXPORT_PRESENT_SHOT_AT": str(frame),
        "SDL_VIDEODRIVER": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "VK_ICD_FILENAMES": os.environ.get("VK_ICD_FILENAMES",
                                           "/usr/share/vulkan/icd.d/radeon_icd.x86_64.json"),
    })
    print(f"[{leg}] settings={settings} aspect={aspect} sink={environment['PSXPORT_PRESENT_SINK']} "
          f"disc={disc}; target presented frame {frame}", flush=True)
    process = subprocess.Popen([str(binary)], cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    result = {"leg": leg, "aspect": aspect, "settings": str(settings),
              "sink": environment["PSXPORT_PRESENT_SINK"], "pid": process.pid,
              "target_frame": frame, "capture": str(capture), "log": str(log),
              "reached_frame": None, "shot_reply": None, "shot_size": None,
              "telemetry": None, "exit": None, "note": ""}
    try:
        from dbgclient import LiveClient
        client = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            if process.poll() is not None:
                result["note"] = (f"the product EXITED on its own (rc={process.returncode}) before "
                                  f"presented frame {frame}")
                break
            try:
                if client is None:
                    client = LiveClient(port=port, timeout=120.0)
                counters = client.frames()
                if counters["frame"] >= frame:
                    result["reached_frame"] = counters["frame"]
                    result["frames_split"] = counters
                    break
                time.sleep(2.0)
            except (OSError, RuntimeError):
                client = None
                time.sleep(2.0)
        else:
            result["note"] = f"NEVER reached presented frame {frame} within {timeout}s"
        if result["reached_frame"] is not None and client is not None:
            result["shot_reply"] = client.shot(str(capture)).strip()
            try:
                result["telemetry"] = parse_telemetry(client.send("guest"))
            except (OSError, RuntimeError, ValueError) as error:
                result["note"] = f"the guest telemetry could not be read: {error}"
            try:
                client.quit()
            except (OSError, RuntimeError):
                pass
    finally:
        try:
            process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            process.terminate()  # this tool's own child, by the captured PID
            process.wait(timeout=60)
        result["exit"] = process.returncode
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    result["wide_lines"] = parse_wide_lines(log_text)
    result["width_verdict"] = classify_wide(result["wide_lines"])
    shots = SHOT_LINE.findall(log_text)
    if shots:
        result["shot_size"] = f"{shots[-1][1]}x{shots[-1][2]}"
    present_shots = PRESENT_SHOT_LINE.findall(log_text)
    if present_shots:
        path, w, h, lit, area, percent = present_shots[-1]
        result["product_present_shot"] = {"path": path, "size": f"{w}x{h}",
                                          "non_black": f"{lit}/{area} ({percent}%)"}
    result["fps60_mentions"] = find_fps60_activity(log_text)
    (SCRATCH / f"leg_{leg}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def report_leg(result: dict, out) -> None:
    out(f"[{result['leg']}] pid={result['pid']} exit={result['exit']} "
        f"reached presented frame {result['reached_frame']} of {result['target_frame']} asked")
    verdict = result["width_verdict"]
    out(f"[{result['leg']}] announced [wide] lines: {verdict.get('announced', 0)}")
    for line in result["wide_lines"]:
        out(f"    log:{line['log_line']}  {line['text']}")
    out(f"[{result['leg']}] steady state (log line {verdict.get('steady_state_log_line')}): "
        f"render_width={verdict.get('render_width')} native_width={verdict.get('native_width')} "
        f"-> render_width > native_width is {verdict.get('widened')}")
    if "reason" in verdict:
        out(f"[{result['leg']}] NO WIDTH VERDICT: {verdict['reason']}")
    out(f"[{result['leg']}] guest-resolution readback: {result['shot_reply']} "
        f"({result['shot_size']})")
    if result.get("product_present_shot"):
        own = result["product_present_shot"]
        out(f"[{result['leg']}] product's own present shot: {own['path']} {own['size']} "
            f"non-black {own['non_black']}")
    if result["telemetry"]:
        keys = ("calls", "translated_blocks", "executed_blocks", "executed_instructions",
                "host_dispatches", "cache_hits", "cache_misses", "invalidations", "faults")
        out(f"[{result['leg']}] guest telemetry: "
            + " ".join(f"{key}={result['telemetry'].get(key)}" for key in keys))
    active = [f for f in result["fps60_mentions"] if f["active"]]
    out(f"[{result['leg']}] fps60: {len(active)} line(s) reporting an ACTIVE fps60 knob, "
        f"{len(result['fps60_mentions']) - len(active)} bare mention(s)")
    for line in result["fps60_mentions"]:
        out(f"    {'ACTIVE' if line['active'] else 'mention'}: {line['text']}")
    if result["note"]:
        out(f"[{result['leg']}] NOTE: {result['note']}")


def selftest(out=print) -> int:
    """Prove the receipt logic reports BOTH answers, then exit.

    The important case is the SECOND one: a tool that can only ever say "widened" is worthless. The
    fixtures are Tekken-shaped — a pre-publication `[wide]` line followed by the steady state, then a
    genuine `render_width == native_width` narrow log, then a log with no `[wide]` line at all, which
    must REFUSE rather than answer. The fourth check is the scope one: this title is 60 fps already
    and must never show an active fps60 row.
    """
    checks = 0
    failures = []

    boot_log = (
        "[wide] native picture: aspect=1 wide_engine=0 native_width=512 render_width=512\n"
        "[wide] native picture: aspect=1 wide_engine=0 native_width=384 render_width=512\n")
    lines = parse_wide_lines(boot_log)
    checks += 1
    if len(lines) != 2:
        failures.append(f"the boot-log fixture has 2 [wide] lines and {len(lines)} were found")
    verdict = classify_wide(lines)
    checks += 1
    if verdict["widened"] is not True or verdict["render_width"] != 512 or verdict["native_width"] != 384:
        failures.append(f"the widened fixture read {verdict}, expected render_width 512 > 384")
    checks += 1
    if verdict["steady_state_log_line"] != 2:
        failures.append(f"the steady state was read from log line {verdict['steady_state_log_line']}, "
                        f"expected the LAST line")

    narrow_log = "[wide] native picture: aspect=0 wide_engine=0 native_width=384 render_width=384\n"
    checks += 1
    if classify_wide(parse_wide_lines(narrow_log))["widened"] is not False:
        failures.append("the narrow fixture was reported as widened; this check can only ever say yes "
                        "if it cannot read the other answer")

    absent = classify_wide(parse_wide_lines("[boot] nothing announced here\n"))
    checks += 1
    if absent["widened"] is not None or "NO [wide] native picture line" not in absent["reason"]:
        failures.append(f"a log with no [wide] line answered {absent}, expected a refusal")

    # The scope check, on both shapes the product uses to report a knob, and on the negative that made
    # this a real check: `Mods::load` has no comment support, so a DOCUMENTED settings file produces
    # `unknown key "# fps60" ignored` on every run, and counting the bare word would report that
    # comment as an enabled enhancement.
    for shape, line, want in (
            ("on value form", "[cfg] PSXPORT_FPS60 = true [env]\n", True),
            ("off value form", "[cfg] PSXPORT_FPS60 = false [default]\n", False),
            ("selection form", "[mod_row] fps60 (selected) on this title\n", True),
            ("refusal form",
             '[mods:warn] config/aspect_4x3.ini: fps60=1 REFUSED — this title declares no temporal '
             'interpolation product\n', True),
            ("comment form",
             '[mods:warn] config/aspect_4x3.ini: unknown key "# fps60" ignored\n', False)):
        checks += 1
        hits = find_fps60_activity(line)
        if not hits or hits[0]["active"] is not want:
            failures.append(f"the {shape} of an fps60 report was classified "
                            f"{hits[0]['active'] if hits else 'not at all'}, expected active={want}")
    checks += 1
    if find_fps60_activity("[mod_row] (no interpolation rows on this title)\n"):
        failures.append("a line with no fps60 knob was reported as an fps60 mention")

    for leg, path in LEG_SETTINGS.items():
        resolved = ROOT / path
        checks += 1
        if not resolved.is_file():
            failures.append(f"tracked settings {path} named by the {leg} leg is missing")
            continue
        text = resolved.read_text(encoding="utf-8")
        checks += 1
        if f"aspect={ASPECT_VALUES[leg]}" not in text:
            failures.append(f"{path} does not pin aspect={ASPECT_VALUES[leg]}; it reads {text!r}")
        checks += 1
        if "fps60=1" in text:
            failures.append(f"{path} enables fps60. Tekken 3 is already 60 fps and its scope is "
                            f"widescreen only, so an fps60 leg is out of scope by policy.")
        # The product must be able to read every line of its own control file. `Mods::load` has no
        # comment support, so a documented settings file makes the product log `unknown key` warnings
        # that read like misconfiguration — and one of those warnings is enough to make a scope check
        # that greps for "fps60" report a knob that is not there.
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            if "=" not in line:
                failures.append(f"{path}:{number} is {line!r}, which `Mods::load` silently skips "
                                f"(no `=`); a control file should have nothing it cannot express")
                continue
            key = line.split("=", 1)[0]
            if key not in SETTINGS_KEYS:
                failures.append(f"{path}:{number} has key {key!r}, which `Mods::load` does not accept; "
                                f"the product will log `unknown key` and configure nothing")

    checks += 1
    try:
        parse_telemetry("no counters at all here")
        failures.append("a reply with no counters was accepted")
    except ValueError:
        pass

    for failure in failures:
        out(f"tekken3 widescreen-pair selftest: FAIL — {failure}")
    if failures:
        out(f"tekken3 widescreen-pair selftest: {checks - len(failures)}/{checks} => FAIL")
        return 1
    out(f"tekken3 widescreen-pair selftest: {checks}/{checks} => PASS (a boot log carrying both the "
        f"pre-publication and the steady-state [wide] line reports the steady state, a 4:3 log reports "
        f"NOT widened, a log with no [wide] line refuses rather than answering, all five shapes the "
        f"product uses to report or misreport an fps60 knob are classified by what they SAY — on value, "
        f"off value, selection, refusal, and a `unknown key` comment that is not an enhancement — "
        f"both tracked settings files pin different aspects with fps60 off, and every line of both "
        f"files is a key `Mods::load` actually accepts)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true", help="prove the receipt logic, then exit")
    parser.add_argument("--leg", choices=sorted(LEG_SETTINGS), help="run ONE aspect leg")
    parser.add_argument("--frame", type=int, default=1200, help="presented frame to capture at")
    parser.add_argument("--port", type=int, default=5961, help="debug endpoint port")
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for the frame")
    parser.add_argument("--binary", default="build/bin/tekken3_port")
    parser.add_argument("--disc", help=f"the user's disc image; defaults to ${DISC_ENV}")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    disc = args.disc or os.environ.get(DISC_ENV)
    if not disc:
        print(f"REFUSED: no disc image. Pass --disc PATH or set {DISC_ENV}. The user's image is "
              f"runtime input and is deliberately not baked into a tracked tool. NOTHING WAS "
              f"MEASURED.", flush=True)
        return 2
    if not pathlib.Path(disc).is_file():
        print(f"REFUSED: disc image {disc} is not a file. NOTHING WAS MEASURED.", flush=True)
        return 2
    binary = ROOT / args.binary
    if not binary.is_file():
        print(f"REFUSED: {binary} does not exist. NOTHING WAS MEASURED.", flush=True)
        return 2

    legs = [args.leg] if args.leg else ["4x3", "16x9"]
    results = []
    for index, leg in enumerate(legs):
        results.append(run_leg(leg, args.frame, args.port + index, binary, args.timeout, disc))
        report_leg(results[-1], print)
    if len(results) != 2:
        return 1
    missing = [r["leg"] for r in results if not pathlib.Path(r["capture"]).is_file()]
    if missing:
        print(f"REFUSED: no capture for the {', '.join(missing)} leg. The run that was supposed to write "
              f"it never reached the checkpoint or failed before the shot — read ITS log. NOTHING WAS "
              f"COMPARED.", flush=True)
        return 2
    import widescreen_pair
    return widescreen_pair.report(results[0]["capture"], results[1]["capture"])


if __name__ == "__main__":
    raise SystemExit(main())
