# `grid-openapi-cases` Claude Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan also REQUIRES the `superpowers:writing-skills` skill — load it before Task 1 and follow its authoring/testing discipline; where the two conflict, writing-skills wins on skill mechanics.

**Goal:** A Claude Code skill that makes any session competent at creating, reading, validating, and converting portable grid case data (OpenAPI document JSON + parquet time series sidecar) with `power-openapi-models` (Python) and `PowerOpenAPIModels` (Julia), so users can adopt the format without reading the tutorials end-to-end.

**Architecture:** One `SKILL.md` (trigger + workflow + hard rules) with three reference files (sidecar contract, model-package cheatsheet, validation recipes). Lives in this repo at `.claude/skills/grid-openapi-cases/` so it travels with the tutorials; the design doc's open question 3 may move it to `~/.claude/skills/`.

**Tech Stack:** Markdown skill per `superpowers:writing-skills`; snippets in both Python and Julia, every one executed before it lands.

**Spec:** `.claude/plans/2026-08-28-openapi-rts-tutorials-design.md` (skill section + sidecar contract)

## Global Constraints

- The skill's audience includes non-Sienna users: body text references Sienna only to say "you do not need it"; package names are the only Sienna surface.
- The sidecar contract in `references/sidecar-contract.md` must be copied from the design doc verbatim — one wording, three documents (two tutorials chapter 07 + this skill).
- Prerequisite: Tasks depend on the two tutorial projects existing (they are the skill's test fixtures and the snippets' source of truth). Execute this plan after the tutorial plans, or stub the pointers and mark them.
- **Git policy:** leave changes unstaged; never commit or push.

---

### Task 1: SKILL.md

**Files:**
- Create: `.claude/skills/grid-openapi-cases/SKILL.md`

**Interfaces:**
- Produces: the skill entry point; frontmatter `name: grid-openapi-cases` and a `description` that triggers on: creating/writing a grid case or system JSON, reading or validating one, the parquet time series sidecar, `power-openapi-models`, `PowerOpenAPIModels`, converting grid data between tools/languages, "portable grid data".

Body sections (each ≤ ~30 lines; detail goes to references):

1. **What a case is** — `system.json` (typed component buckets keyed by type name, integer-id references, association tables, `unit_system`) + `timeseries/` parquet folder. One diagram-free paragraph plus a 15-line example document skeleton.
2. **Which package, which language** — Python: models only, document container is ~150 lines of user code (point at `python/src/rts_gmlc_case/document.py`); Julia: `PowerOpenAPIModels.SystemDocument` provides the container (`add_component!`, `next_id!`, `validate_document`, `write_document`, `read_document`).
3. **Hard rules** — the non-negotiables, one line each: natural units unless the document says otherwise; integer ids minted from one stream, never reused; every reference must resolve before writing; error loudly on unmapped source data (no silent skips); generated model fields are authoritative — enumerate them from the package, never guess; never hand-edit generated model code.
4. **Workflow** — new case: scaffold document → components in dependency order (topology → branches → devices → services) → time series last → validate → write. Reading: parse → validate → resolve `uri`s against the sidecar folder.
5. **Pointers** — the two tutorial projects as worked examples (RTS-GMLC end-to-end), and the three reference files.

- [ ] **Step 1:** load `superpowers:writing-skills`; draft SKILL.md per its structure (frontmatter constraints, description-as-trigger wording).
- [ ] **Step 2:** self-review against writing-skills' checklist (trigger phrasing, length budget, no unexecuted snippets — SKILL.md itself carries at most the document skeleton, which is copied from a real built case).
- [ ] **Step 3: Checkpoint** — leave unstaged, report.

---

### Task 2: `references/sidecar-contract.md`

**Files:**
- Create: `.claude/skills/grid-openapi-cases/references/sidecar-contract.md`

**Interfaces:**
- Produces: the normative sidecar spec both languages implement.

Content: the design doc's sidecar section verbatim (folder name, per-series file naming `ts_<hash16>.parquet`, column types timestamp[ms, UTC] + float64, `data_hash` = SHA-256 over float64-LE bytes, dedup rule, `uri` format, `time_series_storage_file`, association-id minting), followed by the two hash implementations (the Python `data_hash` from the Python plan Task 7 and the Julia `data_hash` from the Julia plan Task 7) and one worked example: the literal hash of `[1.0, 2.0, 3.0]` computed by both.

- [ ] **Step 1:** write it; compute the example hash by actually running both snippets (`python3` one-liner; `julia -e`) and paste the identical output.
- [ ] **Step 2: Checkpoint.**

---

### Task 3: `references/model-cheatsheet.md`

**Files:**
- Create: `.claude/skills/grid-openapi-cases/references/model-cheatsheet.md`

**Interfaces:**
- Produces: how to find and construct model types in both packages.

Content, all verified by execution at write time:

- Domain map: `core` (curves, cost structs, enums, value types) / `operations` (components: buses, branches, generators, loads, reserves) / `timeseries` (the six association types) / `investments` / `dynamics`; same split in both languages (`power_openapi_models.<domain>.models` vs `Power<Domain>OpenAPIModels`).
- Enumeration snippets: Python `python3 -c "from power_openapi_models.operations import models; print([n for n in dir(models) if n[0].isupper()])"`; Julia `names(PowerOperationsOpenAPIModels)` after loading; field listing via `Model.model_fields` / `fieldnames(Model)`.
- Construction idiom: pydantic keyword init with required-field errors vs Julia `@kwdef`-style keyword constructors where unset fields are `nothing`.
- The six time-series association types and when each applies (SingleTimeSeries covers the static case; forecasts named but deferred to the schemas).
- Pitfall list: ids are references, names are not; `bustype`/enum spellings come from the generated enums; per-unit branch impedances ride on the component's `base_power` even in a NATURAL_UNITS document; PTDP's old `rts.json` association shape is stale — trust the packages.

- [ ] **Step 1:** write with executed snippet outputs.
- [ ] **Step 2: Checkpoint.**

---

### Task 4: `references/validation.md`

**Files:**
- Create: `.claude/skills/grid-openapi-cases/references/validation.md`

**Interfaces:**
- Produces: copy-paste validation recipes.

Content: Julia `read_document` + `validate_document` invocation; Python `read_case`-style re-parse loop through pydantic classes; sidecar audit (every `uri` exists; no orphan parquet files; `length` matches row count; `data_hash` re-computes); the cross-language count/hash comparison from the Julia plan Task 10 as the template for verifying any two producers agree.

- [ ] **Step 1:** write it, executing each recipe against the built `cases/rts-*` output.
- [ ] **Step 2: Checkpoint.**

---

### Task 5: Skill testing (writing-skills discipline)

**Files:**
- Modify: any skill file that fails a scenario

- [ ] **Step 1:** fresh-eyes scenario tests via subagents that have the skill loaded but not this conversation's context, e.g.: (a) "create a 3-bus case with one generator and a daily load profile in Python" — must produce a valid document + sidecar without touching Sienna; (b) "validate this case folder and tell me what's wrong" against a deliberately broken copy (dangling bus id, orphan parquet, wrong hash); (c) a trigger test — a prompt about "writing grid data to share between Julia and Python" must surface the skill.
- [ ] **Step 2:** fix the skill where agents stumble (missing constructor idiom, unclear trigger); re-run the failed scenario.
- [ ] **Step 3: Checkpoint** — report scenario outcomes; leave unstaged.
