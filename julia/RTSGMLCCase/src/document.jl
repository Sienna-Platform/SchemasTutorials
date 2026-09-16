using PowerOpenAPIModels: PowerOpenAPIModels

"""
Alias for `PowerOpenAPIModels`, so call sites in this tutorial can write `PD.get_components(...)`
instead of the full module name.
"""
const PD = PowerOpenAPIModels

"""
    new_document() -> PowerOpenAPIModels.SystemDocument

A `SystemDocument` is the shipped container every later stage of this tutorial builds into: typed
component buckets keyed by the producing struct's own name (`"ACBus"`, `"Area"`, ...), plus a
handful of association tables (time series, service, supplemental attributes) that reference
components by a single shared integer id rather than embedding them. There is no document-level
`base_power` or `unit_system` — those are per-component fields set on each component itself
(from chapter 03 onward), not on the document.

`PowerOpenAPIModels.jl` already owns this container, including its own id counter (`next_id!`)
and its bucketing (`add_component!`), so this module does not rebuild one. The Python tutorial
does mint its own id counter here, because `power_openapi_models` ships the container without one
— that asymmetry between the two languages is real, not an oversight this file works around.

The one thing `new_document` supplies is the sidecar folder name, `"timeseries"`: the field is
set once, at construction, because `SystemDocument` is immutable and has no setter for it (see
chapter 08 for what goes in that folder).

To interrogate a document rather than only fill it:

    PD.component_type_names(doc)              # which buckets exist
    length(PD.get_components(doc, "Area"))     # how many components are in one bucket
"""
function new_document()
    return PD.SystemDocument(; time_series_storage_file = "timeseries")
end

"""
    add!(doc, component) -> Int

Bucket `component` into `doc` via `add_component!` and return its id — so later chapters read
`RTSGMLCCase.add!(doc, thing)` the same way the Python tutorial reads
`doc.add_component(thing)`.

`id` is minted by the caller, at construction: the generated structs are immutable and declare
`id` required, so there is no "add it later" to mint into. Every call site therefore reads
`PD.SomeType(; id = PD.next_id!(doc), ...)`, which also makes the id order visible in the source
rather than hidden in this function — the cross-language id-sequence test depends on that order.
"""
function add!(doc::PD.SystemDocument, component::PD.APIModel)
    PD.add_component!(doc, component)
    return component.id
end

"""
    PortfolioCase

A `PortfolioDocument` paired with the `SystemDocument` it expands.

The pair shares one id counter — the *system's* — because the two documents cross-reference: a
technology's `region` names an `ACBus` or `Area` id that lives in the base system, and every
`requirements_associations` row names ids on both sides. Minting from one counter keeps every id
in the pair unique, so a reference is unambiguous about which document it lands in.
"""
struct PortfolioCase
    document::PD.PortfolioDocument
    base::PD.SystemDocument
end

"""
    new_portfolio(base::PD.SystemDocument; aggregation, base_system_file) -> PortfolioCase

An empty investment portfolio built against the system it expands.

A portfolio is its own document — `Investments/PortfolioDocument.json`, not
`Core/SystemDocument.json`. It has required keys a `SystemDocument` has nowhere to put
(`aggregation`, `requirements_associations`, `base_system_file`), so the investments chapters
build into this and the operations chapters into the system.
"""
function new_portfolio(
    base::PD.SystemDocument;
    aggregation::AbstractString,
    base_system_file::AbstractString,
)
    return PortfolioCase(
        PD.PortfolioDocument(
            aggregation;
            base_system_file = base_system_file,
            time_series_storage_file = "timeseries",
        ),
        base,
    )
end


"""
    next_id!(case::PortfolioCase) -> Int

Mint the next unused id from the *base system's* counter, so ids are unique across the pair.
"""
next_id!(case::PortfolioCase) = PD.next_id!(case.base)

"""
    add!(case::PortfolioCase, component) -> Int

Bucket `component` into the portfolio and return its id. Same contract as the `SystemDocument`
method: the caller mints the id at construction.
"""
function add!(case::PortfolioCase, component::PD.APIModel)
    PD.add_component!(case.document, component)
    return component.id
end

"""
    add_requirement_association!(case, requirement_id, entity_id)

Record that the policy requirement `requirement_id` applies to `entity_id`.

This replaces the `requirements` list an earlier version of this tutorial pushed onto the
technology component itself. No release of SiennaSchemas has ever defined that field; the
membership belongs in `requirements_associations`, one row per (requirement, member) pair.
"""
function add_requirement_association!(case::PortfolioCase, requirement_id::Int, entity_id::Int)
    PD.add_requirement_association!(
        case.document,
        PD.RequirementAssociation(; requirement_id = requirement_id, entity_id = entity_id),
    )
    return nothing
end
