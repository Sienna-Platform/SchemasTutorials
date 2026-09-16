# Task JE5 — Julia mirror of E5: policy constraints

Mirrors `python/src/rts_gmlc_case/investments/policy.py` into Julia.
Read it in full — it documents the exact scenario (numbers and
targets), which you must port verbatim, same as JE2 ported Python's
cost figures verbatim. Assumes **JE2 and JE3 are already done and
merged** (needs their `Dict{String,Int}` return values). If either
isn't merged, report BLOCKED.

**Do not run `git add`, `git commit`, or any git write in any repo.** Do
not touch `python/`. Do not change `PowerOpenAPIModels`'s checkout. Do
not modify any existing file except the two `include` list appends.

## The reference mechanism is SIMPLER in Julia than Python — read this
## before writing anything

Python needed a bespoke `CaseDocument.append_requirement` helper because
its components are dumped to plain dicts on `add_component`. **Julia's
components are stored as live mutable struct instances** — `push!`-ing
directly onto a fetched component's `.requirements` field mutates the
document in place, no wrapper needed. Pattern:

```julia
function _find_component(doc::PD.SystemDocument, type_name::AbstractString, id::Int)
    for component in PD.get_components(doc, type_name)
        component.id == id && return component
    end
    error("no $type_name component with id $id")
end
```

then, to attach a policy: `push!(_find_component(doc, "SupplyTechnology",
supply_ids[tech_class]).requirements, policy_id)`. `requirements` on
these structs defaults to `Int64[]` (an empty, already-allocated vector,
not `nothing`) per the generated model — confirmed in
`model_SupplyTechnology.jl`/`model_StorageTechnology.jl` — so `push!`
works directly with no `isnothing` guard needed.

## The exact scenario — verbatim from Python (same numbers/targets, so
## the two cases stay comparable)

Port `investments/policy.py`'s constants and logic directly:

- **`CarbonCaps` x4**: `(2025, 8.0)`, `(2030, 6.5)`, `(2040, 3.5)`,
  `(2050, 1.6)` (`target_year`, `max_mtons`). Targets: `gas-cc`,
  `gas-ct`, `o-g-s`, `coalolduns`.
- **`CarbonTax` x1**: `2030`, `15.0` $/ton. Same 4 targets.
- **`CapacityReserveMargin` x1**: `2030`, `0.13`. Targets: all 9
  `SupplyTechnology` + the 1 `StorageTechnology`.
- **`EnergyShareRequirements` x1**: `2030`, `0.30`. Targets: `upv`,
  `wind-ons`.
- **`MinimumCapacityRequirements` x1**: `2035`, `200.0` MW. Target:
  `wind-ons` only.
- **`MaximumCapacityRequirements` x1**: `2035`, `0.0` MW. Target:
  `coalolduns` only.

Every component: `available = true`, a short `name` (match Python's
naming, e.g. `"Carbon cap 2025"`, for parity, though exact wording isn't
load-bearing).

## New files (flat under `src/`)

- `julia/RTSGMLCCase/src/investments_policy.jl`
- `julia/RTSGMLCCase/test/test_investments_policy.jl`
- Update `RTSGMLCCase.jl`/`test/runtests.jl` includes (after JE2/JE3's
  files).

## What to build

`add_policy_constraints!(doc::PD.SystemDocument, supply_ids::Dict{String,Int},
storage_ids::Dict{String,Int}) -> Dict{String,Vector{Int}}` (policy type
name -> minted ids) — mint each of the 9 policy components via `add!`,
then wire `requirements` via the `_find_component`+`push!` pattern
above, in the same processing order Python's `add_policy_constraints`
uses (CarbonCaps -> CarbonTax -> CapacityReserveMargin ->
EnergyShareRequirements -> MinimumCapacityRequirements ->
MaximumCapacityRequirements).

## Verify (port Python's test assertions, including its
## programmatically-computed expected `requirements` counts — don't
## re-type magic numbers)

- 9 policy components total (4+1+1+1+1+1).
- Every numeric value matches the scenario table exactly.
- Per-technology `requirements` counts match Python's worked table
  exactly (`gas-cc`/`gas-ct`/`o-g-s` = 6, `coalolduns` = 7,
  `hydED`/`hydEND`/`nuclear`/`battery_4` = 1, `upv` = 2, `wind-ons` = 3)
  — compute this expectation programmatically from a declarative
  `{policy_type => target_class_set}` table in your test, not by
  re-typing these numbers as magic literals.
- Every `requirements` entry resolves to a real policy component id.
- `julia --project=. -e 'using RTSGMLCCase'` compiles clean.
- `julia --project=test test/runtests.jl` passes in full, no
  regression on the current baseline.

## Report

Write your full report to `.claude/plans/task-JE5-report.md`. Reply
with only DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED,
compile/test commands and pass counts, and a one-line pointer to the
report file.

If anything here is ambiguous in a way that's load-bearing for JE6/JE7,
ask before guessing.