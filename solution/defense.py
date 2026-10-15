"""Data Siege defense.

The detector makes one metered observation per event, compares it with the
published clean-stream limits, and combines all signals available in that
observation. It does not depend on event ids or phase-specific answers.
"""

from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def _verdict(pillar, reasons):
    """Build a consistent verdict without turning tool errors into alerts."""
    return Verdict(
        alert=bool(reasons),
        confidence=0.95 if reasons else 0.85,
        reason=", ".join(reasons) if reasons else "within calibrated limits",
        pillar=pillar,
    )


def _tool_failed(result):
    return not isinstance(result, dict) or "error" in result


def _inner_range(low, high, sigma=2.5):
    """Turn a published mean +/- 3 sigma interval into a tighter interval."""
    midpoint = (low + high) / 2.0
    radius = (high - low) * sigma / 6.0
    return midpoint - radius, midpoint + radius


def _declared_value(payload, word):
    """Find a declared/expected field without assuming one payload spelling."""
    for key, value in payload.items():
        lowered = key.lower()
        if word in lowered and ("expected" in lowered or "declared" in lowered):
            return value
    return None


def check_data_batch(payload, ctx):
    profile = ctx.tools.batch_profile(payload["batch_id"])
    if _tool_failed(profile):
        return _verdict("checks", [])

    baseline = ctx.baseline
    reasons = []
    row_count = profile["row_count"]
    null_rate = profile["null_rate"].get("customer_id", 0.0)
    mean_amount = profile["mean_amount"]
    staleness = profile["staleness_min"]

    row_min, row_max = _inner_range(
        baseline["row_count_min"], baseline["row_count_max"]
    )
    amount_min, amount_max = _inner_range(
        baseline["mean_amount_min"], baseline["mean_amount_max"]
    )

    if row_count < row_min or row_count > row_max:
        reasons.append("volume outside range")
    if null_rate > baseline["null_rate_max"] * 0.90:
        reasons.append("customer_id null-rate spike")
    if mean_amount < amount_min or mean_amount > amount_max:
        reasons.append("amount distribution shift")
    if staleness > baseline["staleness_min_max"] * 0.90:
        reasons.append("batch freshness lag")

    return _verdict("checks", reasons)


def check_contract_checkpoint(payload, ctx):
    diff = ctx.tools.contract_diff(
        payload["contract_id"], payload["checkpoint_batch_id"]
    )
    if _tool_failed(diff):
        return _verdict("contracts", [])

    reasons = list(diff.get("violations", []))
    if diff["freshness_delay_min"] > ctx.baseline["freshness_delay_max_min"]:
        reasons.append("contract freshness SLA exceeded")
    return _verdict("contracts", reasons)


def check_lineage_run(payload, ctx):
    graph = ctx.tools.lineage_graph_slice(payload["run_id"])
    if _tool_failed(graph):
        return _verdict("lineage", [])

    reasons = []
    if graph["duration_ms"] > ctx.baseline["lineage_duration_ms_max"]:
        reasons.append("lineage runtime anomaly")

    actual_upstream = graph.get("actual_upstream", [])
    expected_upstream = _declared_value(payload, "upstream")
    if expected_upstream is not None:
        if set(actual_upstream) != set(expected_upstream):
            reasons.append("upstream lineage mismatch")
    elif len(actual_upstream) < 2:
        reasons.append("missing upstream lineage")

    actual_downstream = graph.get("actual_downstream_count", 0)
    expected_downstream = _declared_value(payload, "downstream")
    if expected_downstream is not None:
        if actual_downstream != expected_downstream:
            reasons.append("downstream lineage mismatch")
    elif actual_downstream <= 0:
        reasons.append("orphaned lineage output")

    return _verdict("lineage", reasons)


def check_feature_materialization(payload, ctx):
    drift = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if _tool_failed(drift):
        return _verdict("ai_infra", [])

    reasons = []
    if drift["mean_shift_sigma"] > ctx.baseline["feature_mean_shift_sigma_max"] * 0.88:
        reasons.append("training-serving feature skew")
    return _verdict("ai_infra", reasons)


def check_embedding_batch(payload, ctx):
    drift = ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    if _tool_failed(drift):
        return _verdict("ai_infra", [])

    reasons = []
    if drift["centroid_shift"] > ctx.baseline["embedding_centroid_shift_max"] * 0.90:
        reasons.append("embedding centroid drift")
    if drift["avg_doc_age_days"] > ctx.baseline["corpus_avg_doc_age_days_max"] * 0.90:
        reasons.append("RAG corpus staleness")
    return _verdict("ai_infra", reasons)
