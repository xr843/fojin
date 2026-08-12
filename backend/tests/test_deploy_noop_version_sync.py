"""deploy.sh 必须在 no-op 部署时同步 backend/.deploy-version.json。

scheduled smoke 的漂移看门狗拿 /api/version 的 commit 对比 master HEAD。
deploy.sh 对不影响服务进程的提交(eval/tests/docs-only)故意跳过重启——
但部署身份文件仍须推进到新 HEAD(/api/version 每请求重读该文件,bind-mount
下即时生效),否则每次这类合并都会触发"CD stalled"误报(2026-07-10 事故)。

这些测试在临时 git 沙箱里真实运行 deploy.sh:no-op 路径只依赖
git/flock/python3,不会调用 docker/gh/curl,可在 CI 直接执行。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = ROOT / "deploy.sh"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture()
def sandbox(tmp_path):
    """origin(裸仓库) + seed(推送提交用) + work(模拟 VPS 工作树)。"""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-q", "-b", "master", str(origin)], check=True
    )

    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True)
    _git(seed, "checkout", "-q", "-B", "master")
    (seed / "backend" / "eval").mkdir(parents=True)
    (seed / "backend" / "eval" / "report.md").write_text("v1\n", encoding="utf-8")
    (seed / "README.md").write_text("v1\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "c1")
    _git(seed, "push", "-q", "origin", "master")
    base = _git(seed, "rev-parse", "HEAD")

    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    shutil.copy(DEPLOY_SH, work / "deploy.sh")
    state = work / ".deploy-state"
    state.mkdir()
    # 每个服务都要有 marker：缺一个就等于「没有构建记录」，deploy.sh 会判首次
    # 构建并去调 docker，no-op 路径就走不成了。加服务时忘了这一行，症状是这个
    # 测试红在 docker 上，而不是红在它想守的东西上。
    (state / "last-frontend-build").write_text(base + "\n", encoding="utf-8")
    (state / "last-backend-restart").write_text(base + "\n", encoding="utf-8")
    (state / "last-mcp-build").write_text(base + "\n", encoding="utf-8")
    (work / "backend" / ".deploy-version.json").write_text(
        json.dumps(
            {
                "app": "fojin",
                "version": "3.0.0",
                "commit": base,
                "commit_short": base[:7],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return {"seed": seed, "work": work, "base": base}


def _push_commit(sandbox: dict, relpath: str, content: str, msg: str) -> str:
    seed = sandbox["seed"]
    target = seed / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", msg)
    _git(seed, "push", "-q", "origin", "master")
    return _git(seed, "rev-parse", "HEAD")


def _run_deploy(work: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(work / "deploy.sh"), "master"],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _deployed_commit(work: Path) -> str:
    data = json.loads(
        (work / "backend" / ".deploy-version.json").read_text(encoding="utf-8")
    )
    return data["commit"]


def test_eval_only_merge_advances_deploy_identity_without_restart(sandbox):
    new = _push_commit(sandbox, "backend/eval/report.md", "v2\n", "eval only")

    result = _run_deploy(sandbox["work"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "跳过 restart" in result.stdout  # 仍走跳过重启的路径
    assert _deployed_commit(sandbox["work"]) == new  # 但部署身份必须推进


def test_docs_only_merge_advances_deploy_identity(sandbox):
    new = _push_commit(sandbox, "README.md", "v2\n", "docs only")

    result = _run_deploy(sandbox["work"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert _deployed_commit(sandbox["work"]) == new


def test_noop_rerun_with_no_new_commits_stays_clean(sandbox):
    """HEAD 未动的例行 no-op(webhook ping/重跑)也保持身份一致且成功退出。"""
    result = _run_deploy(sandbox["work"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert _deployed_commit(sandbox["work"]) == sandbox["base"]
