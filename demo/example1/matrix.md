# Example1.inp

Model SHA-256 `7a78aab1315a83a5`; 1 raingages, 7 subcatchments, 11 junctions, 1 outfalls, 11 conduits, 1 pollutants; routing DYNWAVE, flow units CFS. Tolerance profile `engineering` (|a - b| <= 0.001 + 0.01 * max(|a|, |b|)).

| Engine | Status | Exit code | Wall s | Results block (SHA-256) | Against its family reference | Runoff cont. % | Routing cont. % |
|---|---|---|---|---|---|---|---|
| swmm5-epa | completed | 0 | 0.223 | `6f44e67b05db` | reference | -0.111 | 0.01 |
| swmm5-cplus | completed | 0 | 0.375 | `6f44e67b05db` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm5-rust | completed | 0 | 0.273 | `6f44e67b05db` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm5-fortran | completed | 0 | 0.388 | `6f44e67b05db` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm5-csharp | completed | 0 | 5.39 | `6f44e67b05db` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm5-python | completed | 0 | 24.9 | `6f44e67b05db` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm5-typescript | completed | 0 | 5.83 | `6f44e67b05db` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm5-java | completed | 0 | 4.49 | `6f44e67b05db` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm5-go | completed | 0 | 0.583 | `6f44e67b05db` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm6-cpp | completed | 0 | 0.574 | `d85c41845c2b` | reference | -0.111 | 0.01 |
| swmm6-csharp | completed | 0 | 3.99 | `d85c41845c2b` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm6-go | completed | 0 | 1.76 | `d85c41845c2b` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm6-java | completed | 0 | 8.62 | `d85c41845c2b` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm6-typescript | completed | 0 | 11.1 | `d85c41845c2b` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm6-fortran | completed | 0 | 1.83 | `d85c41845c2b` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm6-python | completed | 0 | 47.7 | `d85c41845c2b` | IDENTICAL_FILES | -0.111 | 0.01 |
| swmm6-rust | not run: the time-stepping engine and the output writers are unfinished (its README) | - | - | - | - | - | - |

## swmm6-cpp against swmm5-epa

Verdict DIFFERENT: 16 of 82080 values outside the tolerance, worst x14.9. Continuity errors (%): flow routing continuity 0.01 / 0.01; quality routing continuity -1.96 / -1.93; runoff quality continuity 0 / 0; runoff quantity continuity -0.111 / -0.111.

| Kind | Variable | Outside | Compared | Worst x tolerance | Where, when | A | B |
|---|---|---|---|---|---|---|---|
| link | volume | 12 | 3960 | 14.9 | C5 1998-01-01T00:20:00 | 0.23631 | 0.186058 |
| link | quality:TSS | 2 | 3960 | 6.93 | C5 1998-01-01T00:30:00 | 0.170705 | 0.151958 |
| node | quality:TSS | 1 | 4320 | 4.45 | J8 1998-01-02T04:25:00 | 0.138895 | 0.150019 |
| sys | storage_volume | 1 | 360 | 2.09 |  1998-01-01T00:15:00 | 1.55289 | 1.51838 |
| sub | infiltration_loss | 0 | 2520 | 0.958 | S2 1998-01-01T16:25:00 | 0.063989 | 0.0655751 |
| sub | quality:TSS | 0 | 2520 | 0.472 | S4 1998-01-01T12:05:00 | 37.2512 | 37.4284 |
| sub | runoff | 0 | 2520 | 0.207 | S7 1998-01-01T12:05:00 | 3.09828 | 3.09165 |
| node | lateral_inflow | 0 | 4320 | 0.191 | J3 1998-01-01T13:00:00 | 0.467965 | 0.469053 |
