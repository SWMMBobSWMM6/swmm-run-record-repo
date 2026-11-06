# swmm-run-record: one run record for every SWMM engine

Sixteen engines can run a SWMM model here. There are two families:

- **EPA SWMM 5.2.4** and its eight translations: C++, Rust, Fortran, C#, Python, TypeScript, Java and Go.
- **The OpenSWMM 6 1D engine** (HydroCouple `swmm6_rel` 88329d6) and its six translations: C#, Go, Java,
  TypeScript, Fortran and Python.

`swmmrr` runs any of them the same way and writes the same JSON record for every run. It also compares any two
records.

A record says four things:

- **What ran:** the engine, a SHA-256 fingerprint of its build, the commit of the tree it was built from, and what
  its own byte gate showed.
- **On what:** the model, and every file the model reads, each by SHA-256.
- **How it ended:** the status, the exit code, the engine's own ERROR and WARNING lines, and whether the run reached
  the model's end time.
- **What it produced:** the `.rpt` and `.out` by SHA-256, the units, every continuity table, the routing time-step
  summary, the peak of every reporting variable for every object, and any time series asked for.

The schema is `schema/run-record-1.schema.json` (JSON Schema 2020-12). The tool is Python 3 standard library only.

## Use

```
python3 -m swmmrr engines                                   # which engines can run here
python3 -m swmmrr run swmm6-go model.inp -d runs/go         # runs/go/record.json, run.rpt, run.out
python3 -m swmmrr run swmm5-epa model.inp -d runs/epa --series node:J1:depth link:C1:flow sys::runoff
python3 -m swmmrr compare runs/epa/record.json runs/go/record.json --profile engineering -o diff.json
python3 -m swmmrr matrix model.inp -d runs/model            # every engine, compared within and across families
```

Every engine is run the same way: from the model's own folder, as `COMMAND model.inp report.rpt output.out`.

`swmmrr/engines.json` lists the engines. For each one it gives:

- its command, with roots you can override through environment variables;
- the build files whose hashes make up its fingerprint;
- its capabilities;
- its verification, dated.

An engine that cannot run says why, and its capabilities say what it can route, so a 2D or FV task can never be
routed to an engine that lacks that capability. `swmm6-rust`, for example, matches the C++ on all 932 gate decks but has
not translated paths no gate deck reaches (the pressurized implicit FV solver, native hot-start files and a few
more): a deck that needs one stops with exit status 3 and "not translated yet", and the record keeps that (status
`crashed`, exit 3, the message in `stderr_tail`).

## How a run ended

| Status | Meaning |
|---|---|
| `completed` | All four hold: no ERROR line in the report, exit code 0, a complete `.out`, and the last report time at the model's end time. |
| `error` | The engine reported ERROR lines. Their codes and text are in `run.errors`. |
| `crashed` | A nonzero exit (or a signal) with no ERROR line. |
| `timeout` | The run was stopped at the time limit. That makes it untested, not failed. |
| `incomplete` | No ERROR line, but no complete `.out`, or the run stopped short of the end time. |
| `not_run` | The engine cannot run here, and `run.reason` says why. |

The status reads the report and the `.out`, not the exit code alone. EPA SWMM 5.2.4's command line exits 0 even
when the model stops on an input error. Its `main.c` documents something else:

```c
//  Output:  returns error status
...
        swmm_run(inputFile, reportFile, binaryFile);
...
    return 0;
}
```

Every SWMM5 translation keeps that, because the ports are held to EPA's behaviour byte for byte and exit code for
exit code. OpenSWMM 6's command line exits nonzero on an input error (5 for the corpus deck `LEW_update_v5113/Example1.inp`,
which has its sections twice).
The record therefore carries `exit_code_agrees_with_report`, and a batch service built on these engines must read
the status, not the exit code.

## How two records compare

| Verdict | Meaning |
|---|---|
| `IDENTICAL_FILES` | The `.out` files are byte-identical, and the reports are too, apart from their three clock lines. |
| `IDENTICAL_RESULTS` | The `.out` results blocks are byte-identical, but the headers or reports differ. |
| `WITHIN_TOLERANCE` | Every value both files share passes the tolerance test below: every variable of every object, at every report time. |
| `DIFFERENT` | At least one value fails the test. |
| `SAME_ERRORS` / `DIFFERENT_ERRORS` | Both runs stopped on ERROR lines; the verdict says whether the codes match. |
| `NOT_COMPARABLE` | One of three things: different models, one run completed and the other did not, or no report time in common. |

The tolerance test is `|a - b| <= abs + rel * max(|a|, |b|)`. Objects are matched by name, variables by name, and
times to the second. Three profiles set `abs` and `rel`:

| Profile | `abs` | `rel` |
|---|---|---|
| `strict` | 0 | 0 |
| `roundoff` | 1e-6 | 1e-6 |
| `engineering` (the default) | 1e-3 | 1% |

The numbers behind each verdict are always given: for each variable, the count outside the tolerance, the worst
difference as a multiple of the tolerance, and the object, time and both values where it occurs.

A comparison across the two families works the same way. OpenSWMM 6 is a new engine, not a translation of 5.2.4,
so a difference between the families is a finding to explain, not a defect by definition.

## Shown on two models

`demo/example1/matrix.md` and `demo/greenville/matrix.md` are the matrices. Each engine's `record.json` and
`run.rpt` are kept beside them. The large `.out` files are not kept in the repository.

Two models were used:

- **Example 1**, the version in OpenSWMM's regression tests. It has 7 subcatchments, 11 junctions and 11 conduits,
  with dynamic wave routing and one pollutant.
- **Greenville**, `Greenville_all_SWMM5_Features_SI_Units.inp`, the all-features SI model. It has 30
  subcatchments with 186 LID units, 172 nodes, 235 links (5 pumps under 8 control rules), 2 aquifers and 6
  pollutants, with dynamic wave routing and Preissmann slot surcharge. Its 3,000 one-minute report periods hold
  2,462 values each.

Example 1 is one of the SWMM6 ports' 452 extra decks. This Greenville file is in no gate set, SWMM5's or SWMM6's
(the 480 hold a different Greenville model, the six-LID-controls one).

| | Example 1 | Greenville |
|---|---|---|
| The 8 SWMM5 translations against EPA 5.2.4 | all IDENTICAL_FILES | all IDENTICAL_FILES |
| The SWMM6 translations against the OpenSWMM C++ | all 7: IDENTICAL_FILES | all 7: IDENTICAL_FILES |
| OpenSWMM 6 against EPA 5.2.4 (engineering profile) | DIFFERENT: 16 of 82,080 values outside | DIFFERENT: 25,650 of 7,386,000 values (0.35%) outside |
| Continuity error %, runoff / routing (EPA vs OpenSWMM) | -0.111 / 0.01 vs -0.111 / 0.01 | -0.359 / 5.71 vs -0.358 / 5.70 |
| Wall seconds, fastest and slowest translation | swmm6-rust 0.22 s, SWMM6 Python 48 s | SWMM5 C++ 1.9 s, SWMM6 Python 676 s |

On Greenville the two families agree closely where it counts most:

- Every node depth and every link depth is within 1% (or 0.001 m) at every one of the 3,000 report times.
- The continuity errors agree to 0.01%.

The values outside the tolerance are mostly where something switches:

- `PUMP-15`, which a bang-bang control rule starts 1,283 times, is off in one engine at 01:23 on the second day
  and running at 17.5 LPS in the other.
- Inflow to node 83 and volume in its relief conduit R83.
- Subcatchment runoff and evaporation at a few times.

These are differences between two engines, to be explained, not defects. `demo/greenville/cross_family_diff.json`
lists every variable, with the object, time and both values of its worst point.

The matrices also time every engine (on a shared two-core machine with gate runs going, so roughly). Python is the
slow one: 418 s for the SWMM5 translation and 1,669 s for the SWMM6 one, against 4.6 s for EPA on Greenville.

## What this does not show

- **Correctness against the physics.** A record says what an engine produced. Agreement between engines is evidence
  about the translations, not about the hydraulics. The six SWMM6 translations come from one C# translation, so they
  can share its defects; that is why each is gated against the C++ engine, not against the others.
- **Values between report times.** Peaks are taken over the reporting periods of the `.out` file. A peak between
  two report times shows up only in the report's own summary tables, which this record does not read.
- **2D, or more than one thread.** Every engine here is a 1D engine held to one thread.
- **Other machines.** The fingerprints and verification come from the Linux machine the ports were gated on. A
  Windows or browser build needs its own runs.

## License and AI use

Copyright 2026 Robert Dickinson, licensed under the Apache License, Version 2.0 ([LICENSE](LICENSE)). The engines
are separate works under their own licences: EPA SWMM is in the public domain; OpenSWMM 6 is Apache-2.0
(HydroCouple Developers).

Written by Claude (Anthropic) for Robert Dickinson; see [AI-USE.md](AI-USE.md).
