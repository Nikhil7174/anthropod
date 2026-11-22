"""Offline tests for the runner path: schema conversion, prompts, isolation and fallbacks."""

from __future__ import annotations

from call_labeling.evidence_extraction import system_prompt, system_prompt_both, user_message
from call_labeling.evidence_schema import Blockers, BothExtraction, CallbackExtraction, CallFacts
from call_labeling.input_records import CallRecord
from call_labeling.label_one_call import label_record, vote_blockers
from call_labeling.llm_client import LLMError, Usage, parse_json_object, strict_schema
from call_labeling.output_validator import OUTPUT_KEYS, contract_errors

RECORD = CallRecord(
    transcript_id="T-1",
    call_started_at="2026-11-09T14:00:00+05:30",
    timezone="Asia/Kolkata",
    transcript="Agent: Hello, Aster Vale.\nCustomer: My knee hurts, call me tomorrow at 4.\nAgent: Okay.",
)


class FakeClient:
    def __init__(self, responses: dict):
        self.responses = responses

    def complete(self, system, user, schema, name):
        value = self.responses[name]
        if isinstance(value, Exception):
            raise value
        return schema.model_validate(value), Usage(prompt_tokens=100, completion_tokens=10, requests=1)


def _all_objects_strict(node) -> bool:
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            if node.get("additionalProperties") is not False or set(node["required"]) != set(node["properties"]):
                return False
        return all(_all_objects_strict(v) for v in node.values())
    if isinstance(node, list):
        return all(_all_objects_strict(v) for v in node)
    return True


def test_strict_schema_is_closed_and_fully_required():
    for model in (CallFacts, CallbackExtraction, BothExtraction):
        schema = strict_schema(model)
        assert _all_objects_strict(schema)
        assert "default" not in str(schema)


def test_prompts_render_and_user_message_has_weekday():
    for name in ("extract_call_outcome", "extract_callback"):
        prompt = system_prompt(name)
        assert "{time_expr}" not in prompt and "day_ref" in prompt
    msg = user_message(RECORD)
    assert "Monday 09 November 2026" in msg and "T-1" not in msg
    both = system_prompt_both()
    assert "{time_expr}" not in both and both.count("## How to encode a time expression") == 1
    assert "`facts`" in both and "`callback`" in both


def test_happy_path_produces_contract_valid_prediction():
    client = FakeClient({
        "call_facts": {"discussion": {"meaningful_relevant_discussion": True}, "readiness": {"pain_need_established": True}},
        "callback": {"specific_callback_agreed": True, "acknowledged_by_other": True,
                     "options": [{"day_ref": "tomorrow", "hour": 4}]},
    })
    pred, debug = label_record(client, RECORD)
    assert tuple(pred) == OUTPUT_KEYS and contract_errors(pred) == []
    assert pred["sub_disposition"] == "Specific Callback"
    assert pred["next_call_at"] == "2026-11-10T16:00:00+05:30"
    assert debug["usage"]["prompt_tokens"] == 200 and "fallback" not in debug


def test_one_call_returns_the_same_labels_from_one_request():
    client = FakeClient({
        "call_and_callback": {
            "facts": {"discussion": {"meaningful_relevant_discussion": True},
                      "readiness": {"pain_need_established": True}},
            "callback": {"specific_callback_agreed": True, "acknowledged_by_other": True,
                         "options": [{"day_ref": "tomorrow", "hour": 4}]},
        }
    })
    pred, debug = label_record(client, RECORD, calls=1)
    assert pred["sub_disposition"] == "Specific Callback"
    assert pred["next_call_at"] == "2026-11-10T16:00:00+05:30"
    assert debug["llm_calls"] == 1 and debug["usage"]["requests"] == 1
    assert debug["usage"]["prompt_tokens"] == 100


def test_extraction_failure_falls_back_without_raising():
    client = FakeClient({"call_facts": LLMError("boom"), "callback": {}})
    pred, debug = label_record(client, RECORD)
    assert contract_errors(pred) == [] and debug["fallback"] is True
    assert pred["disposition"] == "Follow-up Required" and "boom" in debug["error"]


def test_no_customer_speech_short_circuits():
    rec = RECORD.model_copy(update={"transcript": "Agent: Hello?\nAgent: Hello, can you hear me?"})
    pred, _ = label_record(None, rec)
    assert pred["disposition"] == "Unable to Assess" and pred["next_call_at"] is None


def test_vote_blockers_keeps_only_a_majority():
    blockers = [
        Blockers(primary="travel", final_unresolved=["travel", "family"]),
        Blockers(primary="travel", final_unresolved=["travel"]),
        Blockers(primary="family", final_unresolved=["family", "cost"]),
    ]
    voted = vote_blockers(blockers)
    assert voted.primary == "travel"
    assert voted.final_unresolved == ["family", "travel"]

    split = [
        Blockers(primary="travel", final_unresolved=["travel"]),
        Blockers(primary="family", final_unresolved=["family"]),
        Blockers(primary="cost", final_unresolved=["cost"]),
    ]
    assert vote_blockers(split).primary is None
    assert vote_blockers(split).final_unresolved == []


def test_parse_json_object_tolerates_fences():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_each_provider_requests_the_open_model(monkeypatch):
    from call_labeling.llm_client import JSONClient
    from call_labeling.settings import settings_for

    monkeypatch.delenv("LABELING_MODEL", raising=False)
    cerebras = JSONClient(settings_for("cerebras"), api_key="test")._request([], CallFacts, "call_facts")
    assert cerebras["model"] == "qwen-3.8-27b"
    assert cerebras["temperature"] == 0.0 and cerebras["seed"] == 7
    assert cerebras["reasoning_effort"] == "high"
    assert cerebras["extra_body"] == {"reasoning_format": "parsed"}
    assert "include_reasoning" not in cerebras["extra_body"]

    groq = JSONClient(settings_for("groq"), api_key="test")._request([], CallFacts, "call_facts")
    assert groq["model"] == "qwen/qwen3.8-27b"
    assert groq["extra_body"] == {"include_reasoning": False}


def test_labeling_model_env_overrides_the_default(monkeypatch):
    from call_labeling.settings import settings_for

    monkeypatch.setenv("LABELING_MODEL", "gpt-oss-120b")
    assert settings_for("cerebras").model == "gpt-oss-120b"
    assert settings_for("cerebras", model="qwen-3.8-27b").model == "qwen-3.8-27b"
