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
