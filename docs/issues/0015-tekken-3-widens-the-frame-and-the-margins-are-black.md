---
id: 15
title: Tekken 3 widens to 492 from 368 and the added 62 columns on each side are black, because the only content the product reaches is the 4:3 title card
status: open
symptom: No usable 4:3-versus-16:9 picture pair. The owner fires (`render_width=492` against `native_width=368`) and the widened frame's 62-column margins are 0.00% non-black with every column repeated.
state_items: S005,S006,S007
tags: widescreen,render,evidence,margin-census,title-card,vsync,cadence
created: 2026-09-28
updated: 2026-09-28
---

## Answer

**A picture pair exists and it is a FAILED widening for the checkpoint that is reachable.** The title's
owner widens the frame from 368 to 492 guest pixels, the 4:3 content survives at its original scale and
is re-centred, and both margins are solid black. The `NAMCO PRESENTS` card is a 4:3 presentation
occupying 133x16 pixels; re-centring it into a 492-wide frame is what a *correct* presenter does with
an authored card, and it is not evidence that the widening renders new geometry.

The tool therefore REFUSES the pair, by name, and that refusal is the result. Re-shooting at other
frames until it passes would be manufacturing evidence, exactly as S007 already warned.

## Both legs, from the product

Method: `tools/probe_tekken3_widescreen_pair.py`, two processes, one tracked settings file per leg
(`config/aspect_4x3.ini` / `config/aspect_16x9.ini`, both `fps60=0`), the real
`Tekken 3 (USA).chd`, guest-resolution `shot` readback. Tool selftest 18/18.

| leg | `[wide]` line (steady state) | `render_width > native_width` | guest readback | product's own present shot | content band |
|---|---|---|---|---|---|
| 4:3 | `native_width=368 render_width=368` | **False** | 368x480 | `non-black 1052/276480 (0.38%)` | 133x16 at (117,240) |
| 16:9 | `native_width=368 render_width=492` | **True** | 492x480 | `non-black 955/368640 (0.26%)` | 133x16 at (179,240) |

**The instrument reported both answers** from the same code. The content band is the informative line:
it is **exactly 133x16 in both**, at the same `y`, moved right by 62 px — which is precisely
`(492 - 368) / 2`. The card was re-centred into the wider frame. It was **not** re-projected: a
re-projected card would be wider than 133 px, and this one is not by a single pixel.

## The margin census, with denominators

Measured twice and independently: by `external/psxport/tools/port/widescreen_pair.py`, and by a
separate per-row/per-column scan of the same capture. The two agree exactly.

`external/psxport/tools/port/widescreen_pair.py`, 62-column margins on the 492-wide capture:

    predicted offset for a pure widening : +62
    best translation                     :     0.00 at dx=+62
    next best translation                :     1.34
    worst of 141 offsets tried           :     5.41 at dx=+132
    stretch hypothesis                   :     2.68
    left  margin  62px wide          :   0.0% non-black, 1 colours, 61/61 repeated columns   <- NOT SCENE
    right margin  62px wide          :   0.0% non-black, 1 colours, 61/61 repeated columns   <- NOT SCENE
    REFUSED: ... NOTHING WAS COMPARED at the joins.

Per-row / per-column scan, same file:

| measure | 4:3 whole frame (368 cols) | 16:9 margins (62 cols each side, 124 of 492) |
|---|---|---|
| columns scanned | 368 of 368 | 124 of 492 |
| columns with any non-black pixel | 122/368 (33.2%) | **0/124 (0.0%)** |
| non-black pixels | 1,638/176,640 (0.93%) | **0/59,520 (0.00%)** |
| rows with any non-black pixel | 16/480 (3.3%) | **0/480 (0.0%)** |
| columns identical to their panel's first | — | left **61/61**, right **61/61** |

**Both margins are black: one colour, every column repeated, no row touched.** That is a pillarbox,
and by the criterion in this workspace a pillarboxed margin is a failed widening. It is reported as
one. The join check then REFUSES rather than scoring, because with every column identical there is
no ordinary column-to-column variation for a break to stand out from — the tool's own docstring
records this exact refusal measured on this title's card.

The low `non-black` share of the 16:9 whole frame (0.26% against 0.38%) is the widening's own
arithmetic: the same 955 lit pixels in a wider frame. That ratio moving the *wrong* way is itself a
small independent sign that no new content appeared.

## The simulation was undisturbed by the aspect change

| counter | 4:3 leg | 16:9 leg |
|---|---|---|
| `translated_blocks` | 1,914 | 1,914 |
| `cache_misses` | 1,917 | 1,917 |
| `executed_blocks` | 15,385,466 | 18,153,648 |
| `executed_instructions` | 89,534,251 | 105,617,096 |
| `host_dispatches` | 7,074 | 8,241 |
| `invalidations` | 4,064,675 | 4,771,832 |
| `faults` | 0 | 0 |
| all six `refused_*` reasons | 0 | 0 |
| presented frames reached | 1,254 | 1,482 |
| instructions per presented frame | 71,398 | 71,266 |

**Not byte-identical, and this issue does not claim it.** Both legs stop at the first poll that saw
the frame target, so they ran to different points (1,254 against 1,482 presented frames). Normalised
they are the same trajectory to within 0.19%, and the run-length-independent counters are exactly
equal: 1,914 translated blocks and 1,917 cache misses in both.

## The frame rate: UNMEASURED, and the census that explains why

**Not measured. Not inferred.** The VSync wait semantics were read out of Tekken's own image rather
than assumed, using the shared `external/psxport/tools/disasm.py` over a RAM view built from
`scratch/bin/tekken3/SLUS_004.02` (`scratch/wproof/tekken3.ram`, the authenticated text placed
verbatim at physical `0x00010000`; no guest byte altered).

`FUN_800859A8`, the linked libetc VSync:

    80085A00  bgez   $a0, 0x80085A18     ; a0 >= 0 -> the waiting modes
    80085A04  andi   $s1, $v0, 0xFFFF
    80085A08  lui    $v0, 0x800A
    80085A0C  lw     $v0, -0x5398($v0)  ; negative arm returns *(0x8009AC68) and does NOT wait
    80085A10  j      0x80085B0C          ; straight to the epilogue
    80085A18  addiu  $v0, $zero, 1
    80085A1C  beq    $a0, $v0, 0x80085B08 ; a0 == 1 -> NO WAIT
    80085A24  blez   $a0, 0x80085A44     ; a0 <= 0 -> the non-waiting path
    80085A2C  lui    $v0, 0x800A
    80085A30  lw     $v0, -0x64C4($v0)  ; v0 = the field counter
    80085A38  addiu  $v0, $v0, -1
    80085A40  addu   $v0, $v0, $a0      ; target = current + a0 - 1
    80085A4C  blez   $a0, 0x80085A58
    80085A50  move   $a1, $zero         ; a0 <= 0 -> zero poll budget
    80085A54  addiu  $a1, $a0, -1       ; a1 = a0 - 1
    80085A58  jal    0x80085B20         ; the spin

and the spin at `0x80085B20` polls a genuine per-field counter:

    80085B30  lw     $v0, -0x5398($v0)  ; *(0x8009AC68)
    80085B38  slt    $v0, $v0, $a0      ; field < target ?
    80085B3C  beqz   $v0, 0x80085BA8

**So `a0 == 1` and `a0 <= 0` do not wait; only `a0 >= 2` waits, for `a0` fields.** This is the
established method, measured rather than assumed, and it is the same shape the workspace measured on
Crash Bash.

Now the census. `tools/verify_vsync_field_clock.py` over 295,936 words finds **22** direct `jal
0x800859A8` and names 15 of them `a0 = -1`, one `a0 = 0` (which the semantics above show is also a
no-wait), and refuses to guess 6. **Those 6 were resolved here, by straight-line walk with the same
disassembler:**

| site | definer of `$a0` | argument |
|---|---|---|
| `0x80083938` | `0x80083918 addiu $a0,$zero,-1` | -1, query |
| `0x80083BB8` | `0x80083B98 addiu $a0,$zero,-1` | -1, query |
| `0x800846F0` | `0x800846DC addiu $a0,$zero,-1` | -1, query |
| `0x800910F8` | `0x800910F0 addiu $a0,$zero,-1` | -1, query |
| `0x80091288` | `0x80091264 addiu $a0,$zero,-1` | -1, query |
| `0x8009133C` | `0x80091334 addiu $a0,$zero,-1` | -1, query |

**All 22 of 22 call sites pass `a0 <= 0`. There is no VSync pacing call anywhere in the image.**

That is a strong, and unusual, result: it means the frame rate is **not** negotiated through VSync on
this title, so the VSync argument — the only handle the established method offers — carries no rate
information here at all. It also means this repository's own census tool under-reports: it declared
`0x80091288` UNRESOLVED when the definer sits 0x24 bytes back, inside the same straight-line
prologue. Its refusal was conservative and therefore safe, but "6 unresolved, do not guess" is not
the same as "6 unknown".

**Why the rate is still not measured.** Closing it needs the calls on ONE control-flow path per
frame, and a call-site census cannot recover a path. With 22 of 22 sites non-waiting, the pacing must
come from somewhere this census does not reach — a root counter, a timer, or the main loop's own
structure. None of those was measured here. The honest answer is **unmeasured**, with a denominator
and a named next step, rather than a number inferred from the absence of a wait.

## Scope: no fps60, no interpolation, on this title

Tekken 3 (`SLUS_004.02`) is already 60 fps, so its rendering-enhancement scope is widescreen only.
Both tracked settings files pin `fps60=0`, no interpolation, lerp or temporal path was enabled,
requested or added, and the tool's selftest **fails** if either settings file ever contains `fps60=1`
or if a run reports an fps60 knob as ACTIVE. No such report appeared in either leg.

## A framework finding worth recording: settings files cannot carry comments

Both tracked files were first written with explanatory `#` comments, and the product logged, on every
run:

    [mods:warn] .../config/aspect_4x3.ini: unknown key "# aspect" ignored — it configures nothing
    [mods:warn] .../config/aspect_4x3.ini: unknown key "# fps60" ignored — it configures nothing

`Mods::load` (`runtime/psx/mods.cpp:124-136`) has **no comment support**: it splits every line on the
first `=` and compares the whole prefix as the key, so a comment line containing an `=` is read as a
key named `# <first word>`. A documented settings file therefore makes the product emit
`unknown key` warnings that read exactly like misconfiguration — and in this case one of them was
enough to make the tool's own fps60 scope check report an enhancement that was not running, which is
why the check now classifies each hit by what the line SAYS (an on/off value, a selection state, a
refusal, or a comment) instead of counting the word.

**The tracked files are now comment-free**, and each tool's selftest asserts every line of them is a
key `Mods::load` actually accepts. `Mods::load` gaining `#` handling is a framework change and is not
made here.

## Next step

The blocker is S003, unchanged: the guest cannot leave the title card (issue 0011's SIO0 status
poll), so no 3D stage frame exists to widen. The stage wedge, the 12 right-edge cull comparisons and
the focal-length chain in S006 remain derivation-verified and **product-unobserved** — the gap is a
gameplay frame, not a missing derivation. When one exists, re-run this tool unchanged and take the
census on a frame that carries stage geometry rather than an authored card; on a card, a black margin
is the correct answer and no instrument should be asked to call it anything else.
