"""Behaviour of the commit guards in .githooks/ (ADR-0001).

Each guard runs as a Node child process with no shell and a temporary working directory. The
pre-commit guard runs in its --files mode, so no test calls git or touches the repository.
Samples that name a vendor are built from fragments so this file holds no attribution strings.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1] / ".githooks"
TIMEOUT_SECONDS = 30

_VENDOR = "cla" + "ude"
_MAKER = "anthro" + "pic"
_COAUTHOR = "Co-" + "authored-by"
_SESSION_TRAILER = _VENDOR.title() + "-Session"


def _find_node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.fail(
            "Node.js is required for the hook tests (ADR-0001) but 'node' was not found on PATH.",
            pytrace=False,
        )
    return node


@pytest.fixture(scope="session")
def node() -> str:
    return _find_node()


def _run(node: str, script: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [node, str(HOOKS_DIR / script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


def _run_commit_msg(node: str, tmp_path: Path, message: str) -> subprocess.CompletedProcess[str]:
    message_file = tmp_path / "msg.txt"
    message_file.write_bytes(message.encode())
    return _run(node, "check-commit-msg.mjs", [str(message_file)], tmp_path)


_HEAD = "feat(x): subject\n\nbody\n\n"
_OFFENDERS = {
    "trailer_coauthor": f"{_COAUTHOR}: Someone <someone@example.com>",
    "trailer_session": f"{_SESSION_TRAILER}: abc123",
    "email_noreply": f"Contact noreply@{_MAKER}.com",
    "line_generated_with": "Generated " + "with " + _VENDOR.title() + " Code",
    "link_session": f"https://{_VENDOR}.ai/code/" + "session_01",
}
_REJECTED = {
    **{name: _HEAD + text for name, text in _OFFENDERS.items()},
    **{f"{name}-upper": _HEAD + text.upper() for name, text in _OFFENDERS.items()},
}
_ACCEPTED = {
    "plain": "feat(limits): add a token bucket",
    "tool_named_in_prose": f"docs(readme): explain how to install the {_VENDOR.title()} CLI",
    "body_with_scope": "fix(cache): evict stale keys\n\nKeys older than the window are dropped.\n",
    "comment_line_ignored": f"fix: x\n\n# {_COAUTHOR}: a",
    "midline_mention_ignored": f"docs: ban the {_COAUTHOR}: trailer",
}


@pytest.mark.parametrize("message", list(_REJECTED.values()), ids=list(_REJECTED))
def test_commit_msg_rejects_forbidden_pattern(node: str, tmp_path: Path, message: str) -> None:
    result = _run_commit_msg(node, tmp_path, message)

    assert result.returncode == 1
    assert "Commit rejected" in result.stderr
    assert "line 5:" in result.stderr


@pytest.mark.parametrize("message", list(_ACCEPTED.values()), ids=list(_ACCEPTED))
def test_commit_msg_accepts_normal_message(node: str, tmp_path: Path, message: str) -> None:
    result = _run_commit_msg(node, tmp_path, message)

    assert result.returncode == 0
    assert result.stderr == ""


def test_commit_msg_without_a_file_argument_exits_2(node: str, tmp_path: Path) -> None:
    result = _run(node, "check-commit-msg.mjs", [], tmp_path)

    assert result.returncode == 2


def test_missing_node_fails_instead_of_skipping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda *_args, **_kwargs: None)

    with pytest.raises(pytest.fail.Exception, match=r"Node\.js is required"):
        _find_node()
