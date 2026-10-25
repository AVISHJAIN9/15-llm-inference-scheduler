import pytest
from observability.decision_log import RequestDecisionLogger, DecisionType

def test_SCH_115_request_decision_logs():
    """
    SCH-115: Request decision logs (BE, P0).
    Records all scheduler decisions with strict prompt redaction (§9 Invariant).
    Decision logs contain no prompt text (proven by inspecting stored rows and logs).
    """
    logger = RequestDecisionLogger(max_history=100)

    secret_prompt = "TOP_SECRET_PROMPT_UNAUTHORIZED_LEAK_TEST_12345"

    record = logger.record_decision(
        request_id="req-dec-1",
        tenant_id="tenant-secure",
        model_name="llama-3-8b",
        decision=DecisionType.ADMITTED,
        reason="Capacity available in active continuous batch",
        queue_depth=3,
        active_batch_size=4,
        kv_free_blocks=128,
        prompt=secret_prompt
    )

    # 1. Verify record contains metadata
    assert record.request_id == "req-dec-1"
    assert record.tenant_id == "tenant-secure"
    assert record.decision == DecisionType.ADMITTED
    assert record.queue_depth == 3
    assert record.prompt_length == len(secret_prompt)
    assert record.prompt_redacted is True

    # 2. Strict Redaction Invariant (§9): prompt text is NEVER in stored record dict
    rec_dict = record.to_dict()
    assert "prompt" not in rec_dict
    for v in rec_dict.values():
        assert secret_prompt not in str(v)

    # 3. Serialized records query also excludes raw prompt
    all_records = logger.get_records()
    assert len(all_records) == 1
    retrieved = all_records[0]
    assert retrieved["request_id"] == "req-dec-1"
    assert "prompt" not in retrieved
    assert secret_prompt not in str(retrieved)
