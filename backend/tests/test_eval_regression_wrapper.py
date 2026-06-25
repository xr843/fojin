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
