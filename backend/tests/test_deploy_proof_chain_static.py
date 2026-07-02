"""Static checks for the deploy proof chain."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_deploy_script_writes_runtime_version_file_and_dispatches_smoke():
    deploy_script = (ROOT / "deploy.sh").read_text(encoding="utf-8")

    assert "backend/.deploy-version.json" in deploy_script
    assert "event_type=deploy-success" in deploy_script
    assert "client_payload" in deploy_script
    assert "git rev-parse HEAD" in deploy_script


def test_production_smoke_waits_for_backend_commit_identity():
    smoke_workflow = (ROOT / ".github" / "workflows" / "smoke.yml").read_text(encoding="utf-8")

    assert "/api/version" in smoke_workflow
    assert "EXPECTED_SHA" in smoke_workflow
    assert "client_payload.commit" in smoke_workflow
