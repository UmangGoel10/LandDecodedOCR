from baml_client.types import ConfidenceLevel, FieldValue, LandRecordFields, ListFieldValue

_CONFIDENCE_RANK = {level: rank for rank, level in enumerate(ConfidenceLevel)}


def _empty_value(field: FieldValue | ListFieldValue) -> list[str] | None:
    return [] if isinstance(field, ListFieldValue) else None


def apply_confidence_gate(fields: LandRecordFields) -> LandRecordFields:
    """Null out (or empty, for list fields) the value of any field the LLM
    itself flagged LOW confidence. Iterates over LandRecordFields' actual
    pydantic fields rather than a hand-maintained name list, so this can't
    drift out of sync if the schema changes."""
    updates = {}
    for name in LandRecordFields.model_fields:
        field = getattr(fields, name)
        if field.confidence == ConfidenceLevel.LOW:
            updates[name] = field.model_copy(update={"value": _empty_value(field)})
    return fields.model_copy(update=updates) if updates else fields


def _merge_field(
    claude_field: FieldValue | ListFieldValue,
    gemini_field: FieldValue | ListFieldValue,
) -> FieldValue | ListFieldValue:
    """Reconcile one field pair: higher confidence wins outright. On a tie,
    scalar fields keep the value if both sides agree, else null it. List
    fields (vendors/vendees) keep the intersection instead — names both
    providers independently arrived at survive; a name only one side saw
    is dropped as unconfirmed, but partial agreement isn't thrown away
    the way a full null would."""
    claude_rank = _CONFIDENCE_RANK[claude_field.confidence]
    gemini_rank = _CONFIDENCE_RANK[gemini_field.confidence]

    if claude_rank > gemini_rank:
        return claude_field
    if gemini_rank > claude_rank:
        return gemini_field

    if isinstance(claude_field, ListFieldValue):
        common = [name for name in claude_field.value if name in gemini_field.value]
        return claude_field.model_copy(update={"value": common})

    if claude_field.value == gemini_field.value:
        return claude_field
    return claude_field.model_copy(update={"value": None})


def merge_dual_provider_fields(
    claude_fields: LandRecordFields, gemini_fields: LandRecordFields
) -> LandRecordFields:
    """Reconcile two providers' extractions of the same document, field by
    field, after independently applying the confidence gate to each side."""
    gated_claude = apply_confidence_gate(claude_fields)
    gated_gemini = apply_confidence_gate(gemini_fields)

    updates = {
        name: _merge_field(getattr(gated_claude, name), getattr(gated_gemini, name))
        for name in LandRecordFields.model_fields
    }
    return gated_claude.model_copy(update=updates)
