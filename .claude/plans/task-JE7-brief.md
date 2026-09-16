# Task JE7 — Cross-language equivalence for the combined case

Extends the operations cross-language equivalence check to the combined
(operations + investments) case. Assumes **JE6 is done and merged**, and
that `cases/rts-julia-expansion/` and `cases/rts-expansion/` both exist
on disk as real, freshly-built cases. If either is missing, report
BLOCKED rather than building them yourself (that's JE6's/E6's job, not
this task's).

**Do not run `git add`, `git commit`, or any git write in any repo.** Do
not touch `PowerOpenAPIModels`'s checkout.

## Precedent: the operations-only cross-language check

If `julia/RTSGMLCCase/test/test_cross_language.jl` (or a
`python/tests/test_cross_language.py`) already exists from the original
Julia-tutorial plan's Task 10, read it first and extend it — don't
duplicate a parallel test for the same comparison. If neither exists
(the original Task 10 may not have been executed as part of finishing
the operations tutorial), create one now covering both the
operations-only cases (`cases/rts-python/` vs `cases/rts-julia/`) and
the combined cases (`cases/rts-expansion/` vs `cases/rts-julia-expansion/`)
in one file, since they're the same kind of check at two scopes.

## What to check (the established shallow-equivalence contract — not a
## full field-by-field JSON diff, which is explicitly out of scope per
## the original Julia plan's Task 10, a "stretch" goal only)

For each pair of cases (operations-only, and combined):

1. Same top-level `SystemDocument` keys present in both JSON files.
2. Same set of component-type names in `components`, each with **equal
   count** between the two languages.
3. Same **set** of `data_hash` values across `time_series_associations`
   (not just equal count — the parquet payloads must be byte-identical
   across languages, which is a stronger and more meaningful check than
   count equality alone, and is already how the JO task's own
   operations-only comparison was verified this session — reproduce
   that, don't weaken it to a count-only check).
4. Same count of `service_associations`, `supplemental_attributes`, and
   `supplemental_attribute_associations`.

**R19 — normalize null-valued keys before comparing.** Python writes an
unset optional field as an explicit JSON `null`; Julia's `write_document`
omits the key entirely rather than writing `null` for it (verify this
claim directly against a real component in each of the built cases
rather than assuming — pick one component type that has an optional
field likely to be unset in this case, e.g. `SupplyTechnology.prime_mover_type`,
and check both languages' JSON for it). If any check in this task
compares individual component field sets (not just counts) and hits this
divergence, normalize by treating "key absent" and "key present with
value `null`" as equivalent before comparing, rather than failing on it.
This mainly matters if you compare more than counts/hashes anywhere in
this task's tests.

## New/extended files

- `julia/RTSGMLCCase/test/test_cross_language.jl` (create or extend)
- Update `test/runtests.jl` to include it, if it's a new file.

Skip (with a printed message, not a failure) when any of the four case
directories is missing, rather than erroring — matches the original Task
10's stated behavior.

## Known, already-flagged non-issue

The `ThermalStandard` schema-drift finding (Julia's `PowerOpenAPIModels@main`
ahead of Python's `power_openapi_models` on `status`/`commitment_mode`/
`must_run`) does **not** need to be handled specially by this task's
checks — it doesn't affect component counts or time-series `data_hash`
sets, which is all this task compares. Don't attempt to reconcile it
here; it's recorded in the progress ledger for the user's attention
separately.

## Report

Write your full report to `.claude/plans/task-JE7-report.md`. Report
the exact result of every comparison (counts matched/mismatched per
type, hash-set symmetric difference, any R19 normalization actually
triggered). Reply with only DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT /
BLOCKED, the test command and pass/fail result, and a one-line pointer
to the report file.

If any comparison reveals a genuine mismatch between the Julia and
Python builds (not explained by the already-known, already-accepted
`ThermalStandard` drift), that's a real finding — report it clearly
rather than adjusting the test to pass. Don't guess at a fix without
checking with me first if the mismatch's cause isn't immediately
obvious from the data.