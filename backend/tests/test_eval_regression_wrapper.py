"""The host-side answer-quality regression cron wrapper (fojin-eval-regression.sh)
must, at minimum:

  1. propagate the gate's exit code (a swallowed non-zero would let a retrieval
     regression ship while the cron reports success — the exact "gate quietly
     stops working" failure the gate exists to prevent), and
  2. fire a Telegram alert ONLY when the gate fails (no alert on a green run, so
     the signal stays meaningful), and
  3. never crash or mask a regression when Telegram creds are absent.

The gate command and Telegram endpoint are injected via env so this runs in CI
with no docker and no network — only the wrapper's own control flow is exercised.
"""

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "fojin-eval-regression.sh"


def _run(tmp_path, *, gate_exit: int, bot_token="test-token", chat_id="test-chat"):
    """Invoke the wrapper with a fake gate command and a fake `curl` on PATH.

    The fake curl appends each invocation's args to a marker file so the test can
    assert whether (and how) an alert was attempted without any network. Pass
    ``bot_token=None`` / ``chat_id=None`` to drop that cred from the environment.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "curl-calls.txt"
    fake_curl = bindir / "curl"
    fake_curl.write_text("#!/usr/bin/env bash\n" f'printf "%s\\n" "$*" >> "{marker}"\n')
    fake_curl.chmod(0o755)

    gate = tmp_path / "fake_gate.sh"
    gate.write_text(
        "#!/usr/bin/env bash\n"
        'echo "  ⚠️  Recall@5 0.31 低于下限 0.40"\n'
        f"exit {gate_exit}\n"
    )
    gate.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["EVAL_GATE_CMD"] = str(gate)
    env["FOJIN_DIR"] = str(tmp_path)  # don't cd into a real /home/admin/fojin
    env["TELEGRAM_API_BASE"] = "http://127.0.0.1:0"  # never hit; curl is faked
    for key, val in (("TELEGRAM_BOT_TOKEN", bot_token), ("TELEGRAM_CHAT_ID", chat_id)):
        if val is None:
            env.pop(key, None)
        else:
            env[key] = val

    proc = subprocess.run(
        ["bash", str(WRAPPER)], env=env, capture_output=True, text=True
    )
    calls = marker.read_text() if marker.exists() else ""
    return proc, calls


def test_gate_pass_exits_zero_and_sends_no_alert(tmp_path):
    proc, calls = _run(tmp_path, gate_exit=0)
    assert proc.returncode == 0
    assert calls == "", f"alert must NOT fire on a green gate; got: {calls!r}"


def test_gate_fail_propagates_exit_and_alerts(tmp_path):
    proc, calls = _run(tmp_path, gate_exit=1)
    assert proc.returncode == 1, "wrapper must propagate the gate's non-zero exit"
    assert "sendMessage" in calls, "a Telegram alert must fire when the gate fails"
    assert "test-token" in calls, "alert must target the configured bot token"
    assert "Recall@5" in calls, "the gate's failure detail must reach the alert"


def test_gate_fail_without_creds_still_propagates_exit(tmp_path):
    proc, calls = _run(tmp_path, gate_exit=1, bot_token=None, chat_id=None)
    assert proc.returncode == 1, "missing creds must not mask the regression"
    assert calls == "", "no creds → no curl attempt"


def test_gate_fail_with_partial_creds_skips_alert_but_still_fails(tmp_path):
    # Token set, chat_id missing: the wrapper requires BOTH (the `&&` guard), so it
    # must skip the alert yet still propagate the regression. Locks that guard
    # against a future refactor to `||` that would attempt a malformed alert.
    proc, calls = _run(tmp_path, gate_exit=1, chat_id=None)
    assert proc.returncode == 1, "partial creds must not mask the regression"
    assert calls == "", "incomplete creds → no curl attempt"


# ──────────────────────────────────────────────────────────────────────
# run_eval's own baseline gate had the very failure this wrapper guards
# against: an unreadable or corrupt --baseline printed a note and fell
# through with gate_failed still False, so --fail-on-regression exited 0.
# "Could not compare" is not "no regression".
# ──────────────────────────────────────────────────────────────────────


def test_missing_baseline_file_reports_an_error_not_a_clean_comparison(tmp_path):
    from eval.run_eval import compare_baseline

    regressions, error = compare_baseline(
        str(tmp_path / "does-not-exist.json"), current_agg={}, current_faith={}
    )
    assert error is not None
    assert regressions == []


def test_corrupt_baseline_json_reports_an_error(tmp_path):
    from eval.run_eval import compare_baseline

    bad = tmp_path / "baseline.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    regressions, error = compare_baseline(str(bad), current_agg={}, current_faith={})
    assert error is not None


def test_readable_baseline_compares_cleanly(tmp_path):
    from eval.run_eval import compare_baseline

    good = tmp_path / "baseline.json"
    good.write_text("[]", encoding="utf-8")
    regressions, error = compare_baseline(str(good), current_agg={}, current_faith={})
    assert error is None
    assert regressions == []


# --- test-set version guard ------------------------------------------------
# Changing the gold set changes what the numbers MEAN. Comparing a v1.3 run
# against a v1.2 baseline manufactures phantom regressions (or hides real ones),
# so a version mismatch must surface as an error, not as a clean comparison.

def test_baseline_from_an_older_ruler_is_an_error_not_a_clean_pass(tmp_path):
    from eval.run_eval import compare_baseline

    old = tmp_path / "baseline-v12.json"
    old.write_text(json.dumps([
        {"id": "term-001", "test_set_version": "1.2",
         "retrieval_metrics": {"recall@5": 0.9, "hit@5": 1.0}},
    ]), encoding="utf-8")

    regressions, error = compare_baseline(
        str(old), current_agg={"recall@5": 0.2}, current_faith={}, current_version="1.3"
    )
    assert regressions == []
    assert error is not None and "1.2" in error and "1.3" in error


def test_unstamped_baseline_is_treated_as_older_ruler(tmp_path):
    from eval.run_eval import compare_baseline

    legacy = tmp_path / "baseline-legacy.json"
    legacy.write_text(json.dumps([
        {"id": "term-001", "retrieval_metrics": {"recall@5": 0.9}},
    ]), encoding="utf-8")

    _, error = compare_baseline(
        str(legacy), current_agg={"recall@5": 0.2}, current_faith={}, current_version="1.3"
    )
    assert error is not None


def test_same_version_baseline_still_compares(tmp_path):
    from eval.run_eval import compare_baseline

    same = tmp_path / "baseline-v13.json"
    same.write_text(json.dumps([
        {"id": "term-001", "test_set_version": "1.3",
         "retrieval_metrics": {"recall@5": 0.50}},
    ]), encoding="utf-8")

    regressions, error = compare_baseline(
        str(same), current_agg={"recall@5": 0.20}, current_faith={}, current_version="1.3"
    )
    assert error is None
    assert any("recall@5" in r for r in regressions)


def test_version_check_is_skipped_when_caller_passes_no_version(tmp_path):
    # Back-compat: existing callers/tests that omit current_version keep working.
    from eval.run_eval import compare_baseline

    b = tmp_path / "b.json"
    b.write_text(json.dumps([{"id": "x", "retrieval_metrics": {"recall@5": 0.5}}]), encoding="utf-8")
    _, error = compare_baseline(str(b), current_agg={"recall@5": 0.5}, current_faith={})
    assert error is None


# --- eval/run_regression.sh's own control flow ------------------------------
# The wrapper tests above inject a fake gate, so run_regression.sh itself was
# never executed by any test. Its two branches decide whether answer quality
# gets measured at all and whether a broken ruler is allowed through — both are
# exactly the "gate quietly stops gating" shape this file exists to prevent.

GATE = Path(__file__).resolve().parents[1] / "eval" / "run_regression.sh"


def _run_gate(tmp_path, *, reachable_exit=0, extra_env=None):
    """Run run_regression.sh with a fake `python` that records its args."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "python-calls.txt"
    (bindir / "python").write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >> "{calls}"\n'
        f'case "$*" in *check_gold_reachable*) exit {reachable_exit};; esac\n'
        "exit 0\n"
    )
    (bindir / "python").chmod(0o755)

    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps([]), encoding="utf-8")

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["BASELINE"] = str(baseline)
    env.pop("LLM", None)
    env.update(extra_env or {})

    proc = subprocess.run(["bash", str(GATE)], env=env, capture_output=True, text=True)
    return proc, (calls.read_text() if calls.exists() else "")


def test_gate_checks_the_ruler_before_measuring_with_it(tmp_path):
    proc, calls = _run_gate(tmp_path, reachable_exit=1)
    assert proc.returncode != 0
    assert "check_gold_reachable" in calls
    # must NOT have gone on to measure with a ruler it just rejected
    assert "run_eval" not in calls


def test_gate_defaults_to_retrieval_only(tmp_path):
    proc, calls = _run_gate(tmp_path)
    assert proc.returncode == 0
    assert "--no-llm" in calls
    assert "--temperature" not in calls


def test_llm_env_switches_to_full_eval_at_temperature_zero(tmp_path):
    proc, calls = _run_gate(tmp_path, extra_env={"LLM": "1"})
    assert proc.returncode == 0
    run_eval_call = [ln for ln in calls.splitlines() if "run_eval" in ln][0]
    assert "--no-llm" not in run_eval_call
    assert "--temperature 0" in run_eval_call
