# Greenville_all_SWMM5_Features_SI_Units.inp

Model SHA-256 `5808a9bad783d64d`; 2 raingages, 30 subcatchments, 149 junctions, 5 outfalls, 1 dividers, 17 storage, 223 conduits, 5 pumps, 2 orifices, 4 weirs, 1 outlets, 6 pollutants, 27 lid_controls, 186 lid_usage, 8 control_rules, 2 aquifers; routing DYNWAVE, flow units LPS. Tolerance profile `engineering` (|a - b| <= 0.001 + 0.01 * max(|a|, |b|)).

| Engine | Status | Exit code | Wall s | Results block (SHA-256) | Against its family reference | Runoff cont. % | Routing cont. % |
|---|---|---|---|---|---|---|---|
| swmm5-epa | completed | 0 | 2.02 | `d0dc979565a2` | reference | -0.359 | 5.71 |
| swmm5-cplus | completed | 0 | 1.87 | `d0dc979565a2` | IDENTICAL_FILES | -0.359 | 5.71 |
| swmm5-rust | completed | 0 | 2.33 | `d0dc979565a2` | IDENTICAL_FILES | -0.359 | 5.71 |
| swmm5-fortran | completed | 0 | 2.47 | `d0dc979565a2` | IDENTICAL_FILES | -0.359 | 5.71 |
| swmm5-csharp | completed | 0 | 6.19 | `d0dc979565a2` | IDENTICAL_FILES | -0.359 | 5.71 |
| swmm5-python | completed | 0 | 181 | `d0dc979565a2` | IDENTICAL_FILES | -0.359 | 5.71 |
| swmm5-typescript | completed | 0 | 27.2 | `d0dc979565a2` | IDENTICAL_FILES | -0.359 | 5.71 |
| swmm5-java | completed | 0 | 7.95 | `d0dc979565a2` | IDENTICAL_FILES | -0.359 | 5.71 |
| swmm5-go | completed | 0 | 3.75 | `d0dc979565a2` | IDENTICAL_FILES | -0.359 | 5.71 |
| swmm6-cpp | completed | 0 | 6.14 | `aa2bb947f288` | reference | -0.358 | 5.7 |
| swmm6-csharp | completed | 0 | 15.5 | `aa2bb947f288` | IDENTICAL_FILES | -0.358 | 5.7 |
| swmm6-go | completed | 0 | 23.3 | `aa2bb947f288` | IDENTICAL_FILES | -0.358 | 5.7 |
| swmm6-java | completed | 0 | 16 | `aa2bb947f288` | IDENTICAL_FILES | -0.358 | 5.7 |
| swmm6-typescript | completed | 0 | 83.4 | `aa2bb947f288` | IDENTICAL_FILES | -0.358 | 5.7 |
| swmm6-fortran | completed | 0 | 72.8 | `aa2bb947f288` | IDENTICAL_FILES | -0.358 | 5.7 |
| swmm6-python | completed | 0 | 676 | `aa2bb947f288` | IDENTICAL_FILES | -0.358 | 5.7 |
| swmm6-rust | completed | 0 | 5.78 | `aa2bb947f288` | IDENTICAL_FILES | -0.358 | 5.7 |

## swmm6-cpp against swmm5-epa

Verdict DIFFERENT: 25650 of 7386000 values outside the tolerance, worst x99.4. Continuity errors (%): flow routing continuity 5.71 / 5.7; groundwater continuity 0 / 0; runoff quantity continuity -0.359 / -0.358.

| Kind | Variable | Outside | Compared | Worst x tolerance | Where, when | A | B |
|---|---|---|---|---|---|---|---|
| link | flow | 11680 | 705000 | 99.4 | PUMP-15 1997-01-02T01:23:00 | 0 | 17.5019 |
| link | volume | 6658 | 705000 | 46.5 | R83 1997-01-02T05:31:00 | 1.79588 | 0.914503 |
| node | total_inflow | 6037 | 516000 | 96.4 | 83 1997-01-02T02:16:00 | 2.82561 | 0.00631307 |
| link | capacity | 414 | 705000 | 90.9 | PUMP-15 1997-01-02T01:23:00 | 0 | 1 |
| sys | outfall_outflow | 334 | 3000 | 34.4 |  1997-01-02T13:28:00 | 5.54846 | 3.60427 |
| link | velocity | 331 | 705000 | 72.1 | 3629 1997-01-01T00:42:00 | 0 | 0.258023 |
| sub | evaporation_loss | 93 | 90000 | 26.2 | C13 1997-01-02T21:17:00 | 0.0187236 | 0.0608914 |
| node | volume | 63 | 516000 | 3.74 | 83 1997-01-02T05:31:00 | 0.00388695 | 0 |
