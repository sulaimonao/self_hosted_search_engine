from backend.app.io.adapters import normalize_model_alias
from backend.app.jobs import diagnostics as diag_jobs


def test_llama2_alias_normalizes_to_primary_model():
    assert normalize_model_alias("llama2") == "gpt-oss"



def test_diagnostics_snapshot_reports_llama2_alias():
    snapshot = diag_jobs._chat_alias_snapshot()  # noqa: SLF001 - intentional diagnostic coverage
    matches = [entry for entry in snapshot.get("checks", []) if entry.get("alias") == "llama2"]
    assert matches, "llama2 alias missing from diagnostics snapshot"
    assert matches[0]["ok"] is True
    assert matches[0]["normalized"] == "gpt-oss"
