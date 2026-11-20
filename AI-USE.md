# How AI was used in swmm-run-record

swmm-run-record was written by Claude (Anthropic's AI model, Claude Opus 5.5), in a Claude Code session, working
for Robert Dickinson.

- **What Claude wrote:** all of it: the `.out` and `.rpt` readers, the engine registry, the run record and its
  JSON Schema, the comparison, the command line, the demonstrations and this repository's text.
- **What Claude did not write:** the engines the registry runs. EPA SWMM 5.2.4 is the U.S. EPA's; OpenSWMM 6 is
  HydroCouple's. The translations (swmm5-cplus, swmm5-rust, the SWMM5 and SWMM6 ports in C#, Go, Java,
  TypeScript, Fortran and Python) were also made by Claude for Robert Dickinson, in earlier sessions, and carry
  their own AI-USE notes.
- **How the work was checked:** by running it. Every record in `demo/` validates against
  `schema/run-record-1.schema.json`; the comparison was checked on identical pairs (a record against itself gives
  IDENTICAL_FILES), on engines known to match byte for byte (the byte gates of each port), on two engines known to
  differ (EPA SWMM 5.2.4 and OpenSWMM 6), and on the timeout and input-error paths.
- **Human direction:** Robert Dickinson asked for the shared result format, chose to have it shown on one small
  model and on Greenville, and reviews the results. Responsibility for publishing the work is his.

## 19 November 2026: the type-code correction (swmmrr 1.0.1)

Made with Claude (Anthropic's AI model, Claude Fable 5.2), in one session, at Robert Dickinson's request: Claude had
found the fault while checking another reader against this one, reported it to him with the offending lines, and he
asked for the fix and for the demo records to be put right.

- **What Claude did:** corrected the `.out` reader (type codes read as integers, and by each engine's own numbering),
  wrote the `reread` command, the `corrections` entry of the schema and the tests, ran swmm5-rust and swmm6-rust to
  produce the four `.out` files again, applied `reread` to the 34 demo records, and wrote the Corrections section of
  the README.
- **How it was checked:** mechanically. The four `.out` files have the SHA-256 the records name. With the old reader
  the procedure reproduces all 34 records exactly. With the new one only type fields change (799 values), and the
  corrected types equal the `.inp` sections (7,310 comparisons). The tests run on real output of both engine
  families and fail against the old reader. Every record validates against the schema.
- **What no person has checked:** the code and the corrected records have not been reviewed by a person. Whether
  OpenSWMM 6 means to number STORAGE and DIVIDER differently from SWMM 5 in a SWMM 5 format file has not been asked
  of its developers.
