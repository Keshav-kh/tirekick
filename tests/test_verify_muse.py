"""muse.py: structured output, fallbacks, retry policy, raw-output logging, web-search parsing."""

import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import BaseModel

from tirekick import config
from tirekick.verify import muse
from tirekick.verify.listing import ListingExtract
from tirekick.verify.proof_take import TakeObservation


class Car(BaseModel):
    make: str
    year: int | None = None


def err(cls, status, msg="error"):
    req = httpx.Request("POST", "https://api.meta.ai/v1/chat/completions")
    return cls(msg, response=httpx.Response(status, request=req), body={"message": msg})


def reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)


@pytest.fixture
def fake(monkeypatch):
    """Install a scripted client. Each script item is a reply string or an exception to raise."""
    sleeps = []
    monkeypatch.setattr(muse, "_sleep", sleeps.append)

    def install(chat=(), responses=()):
        chat_q, resp_q, calls = list(chat), list(responses), {"chat": [], "responses": []}

        def nxt(q, kind, kw):
            calls[kind].append(kw)
            item = q.pop(0)
            if isinstance(item, Exception):
                raise item
            return item if not isinstance(item, str) else (reply(item) if kind == "chat"
                                                            else SimpleNamespace(output_text=item, usage=None))

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: nxt(chat_q, "chat", kw))),
            responses=SimpleNamespace(create=lambda **kw: nxt(resp_q, "responses", kw)),
        )
        monkeypatch.setattr(muse, "_client", client)
        calls["sleeps"] = sleeps
        return calls
    return install


def runs_logged():
    d = config.DATA_DIR / "runs"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.exists() else []


def test_strict_schema_inlines_refs_and_closes_objects():
    s = muse.strict_schema(TakeObservation)
    text = json.dumps(s)
    assert "$ref" not in text and "$defs" not in text
    assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
    light = s["properties"]["lights"]["items"]
    assert light["additionalProperties"] is False and "enum" in json.dumps(light["properties"]["light"])
    assert "title" in muse.strict_schema(ListingExtract)["properties"]   # a field named "title" survives


def test_structured_output_happy_path_and_raw_log(fake):
    calls = fake(chat=['{"make": "Honda", "year": 2015}'])
    out = muse.muse_json([{"role": "user", "content": "x"}], Car, tag="t")
    assert out == Car(make="Honda", year=2015)
    rf = calls["chat"][0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["name"] == "Car"
    assert calls["chat"][0]["model"] == "muse-spark-1.3"
    log = runs_logged()[-1]
    assert log["response"] == '{"make": "Honda", "year": 2015}' and log["structured"] is True


def test_schema_rejected_falls_back_to_json_only(fake):
    calls = fake(chat=[err(openai.BadRequestError, 400, "response_format json_schema not supported"),
                       'Sure! ```json\n{"make": "Honda"}\n```'])
    assert muse.muse_json([{"role": "user", "content": "x"}], Car).make == "Honda"
    assert "response_format" not in calls["chat"][1]
    assert "JSON only" in calls["chat"][1]["messages"][-1]["content"]


def test_temperature_rejected_is_dropped(fake):
    calls = fake(chat=[err(openai.BadRequestError, 400, "temperature is not supported for this model"),
                       '{"make": "Honda"}'])
    assert muse.muse_json([{"role": "user", "content": "x"}], Car).make == "Honda"
    assert "temperature" not in calls["chat"][1] and "response_format" in calls["chat"][1]


def test_validation_error_repaired_once(fake):
    calls = fake(chat=['{"year": 2015}', '{"make": "Honda", "year": 2015}'])
    assert muse.muse_json([{"role": "user", "content": "x"}], Car).make == "Honda"
    assert "failed validation" in calls["chat"][1]["messages"][-1]["content"]


def test_validation_error_twice_raises(fake):
    fake(chat=['{"year": 1}', '{"year": 2}'])
    with pytest.raises(muse.MuseError, match="no valid JSON"):
        muse.muse_json([{"role": "user", "content": "x"}], Car)


def test_429_and_5xx_retried_with_backoff(fake):
    calls = fake(chat=[err(openai.RateLimitError, 429), err(openai.InternalServerError, 503), '{"make": "Kia"}'])
    assert muse.muse_json([{"role": "user", "content": "x"}], Car).make == "Kia"
    assert calls["sleeps"] == [1.0, 2.0]
    assert sum(1 for r in runs_logged() if "error" in r) == 2


def test_gives_up_after_backoff_schedule(fake):
    calls = fake(chat=[err(openai.InternalServerError, 500)] * 4)
    with pytest.raises(muse.MuseError):
        muse.muse_json([{"role": "user", "content": "x"}], Car)
    assert calls["sleeps"] == [1.0, 2.0, 4.0] and len(calls["chat"]) == 4


def test_auth_error_not_retried(fake):
    calls = fake(chat=[err(openai.AuthenticationError, 401)])
    with pytest.raises(muse.MuseError):
        muse.muse_json([{"role": "user", "content": "x"}], Car)
    assert len(calls["chat"]) == 1 and calls["sleeps"] == []


def test_responses_json_uses_text_format(fake):
    calls = fake(responses=['{"make": "Toyota"}'])
    out = muse.responses_json([{"type": "input_text", "text": "x"}], Car, instructions="sys")
    assert out.make == "Toyota"
    kw = calls["responses"][0]
    assert kw["text"]["format"]["type"] == "json_schema" and "response_format" not in kw
    assert kw["instructions"] == "sys" and kw["input"][0]["role"] == "user"


def test_base64_media_redacted_in_logs(fake, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8" + b"x" * 5000)
    fake(chat=['{"make": "Honda"}'])
    muse.muse_json([{"role": "user", "content": [muse.text_part("x"), muse.image_part(img)]}], Car)
    raw = json.dumps(runs_logged()[-1])
    assert ";base64," not in raw and "<image/jpeg data URL" in raw


def test_api_key_accepts_meta_or_model_var(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_API_KEY", "LLM|1|s")
    assert muse.api_key() == "LLM|1|s" and muse.available()


SEARCH_RESPONSE = {
    "output": [
        {"type": "reasoning"},
        {"type": "web_search_call", "status": "completed"},
        {"type": "message", "content": [{
            "type": "output_text", "text": "Prices: A $9,000; B $9,500.",
            "annotations": [
                {"type": "url_citation", "url": "https://a.example/1", "title": "A", "start_index": 8, "end_index": 16},
                {"type": "url_citation", "url": "https://b.example/2", "title": "B", "start_index": 18, "end_index": 26},
            ]}]},
    ],
    "output_text": "Prices: A $9,000; B $9,500.",
}


def test_parse_search_response():
    r = muse.parse_search_response(SEARCH_RESPONSE)
    assert r.searched and r.text.startswith("Prices")
    assert [c.url for c in r.citations] == ["https://a.example/1", "https://b.example/2"]


def test_web_search_request_shape(fake):
    calls = fake(responses=[SEARCH_RESPONSE])
    r = muse.web_search("find comps", instructions="be precise")
    kw = calls["responses"][0]
    assert kw["tools"] == [{"type": "web_search", "search_context_size": "medium"}]
    assert "response_format" not in kw and r.searched and len(r.citations) == 2


def test_extract_json_from_prose():
    assert json.loads(muse.extract_json('Here you go:\n{"a": [1, 2]}\nThanks')) == {"a": [1, 2]}
