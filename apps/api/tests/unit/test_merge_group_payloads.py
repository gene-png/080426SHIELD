"""Replay recorded `merge_group` payloads through the workflows' own resolver steps.

The merge queue needs the repo to live in an organization, so nothing here can
run live yet (#659). This is the stand-in: a RECORDED `checks_requested`
payload, fed through each body job's "Read the queued PR (merge_group)" step
exactly as the workflow spells it -- its `env:` expressions resolved against the
payload, its `run:` line split and executed against `scripts.merge_group_pr` --
with `gh` and `git` replaced in-process.

That catches what the resolver's own unit tests cannot: a workflow expression
naming a payload field that does not exist (`merge_group.headref`) resolves to
an empty string on GitHub, with no error. Here it is a KeyError.

## The payloads

`octokit_checks_requested.json` is octokit/webhooks'
`payload-examples/api.github.com/merge_group/checks_requested.payload.json`,
byte-for-byte as downloaded on 2026-10-15. It is a recorded example, not a
GitHub-signed capture from this repo; its `head_commit` does not even agree
with its own `head_sha` and `head_ref` (another PR number, another sha), which
is why nothing in this repo reads `head_commit`.

`unparseable_ref.json` and `no_such_pr.json` are that payload with ONLY
`merge_group.head_ref` changed, which
`test_the_derived_payloads_differ_only_in_the_ref` pins.
"""

from __future__ import annotations

import json
import pathlib
import re
import shlex

import pytest
import yaml

from tests._paths import find_workflows_dir

_WORKFLOWS_DIR = find_workflows_dir(pathlib.Path(__file__).resolve())
if _WORKFLOWS_DIR is None:  # pragma: no cover - container-only branch
    pytest.skip(
        "no .github/workflows above this file -- expected inside the api container",
        allow_module_level=True,
    )

import scripts.merge_group_pr as resolver  # noqa: E402

_PAYLOADS = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "merge_group"
_RECORDED = "octokit_checks_requested.json"
_JOBS = ("Adversarial audit recorded", "No accidental issue closes")
_PR_HEAD = "c" * 40
_TREE = "e" * 40
#: Where the workflow steps write their files; remapped into tmp_path here.
_WORKFLOW_TMP = "/tmp/"  # noqa: S108 - a literal in the workflow, not a temp file


def _payload(name: str) -> dict:
    return json.loads((_PAYLOADS / name).read_text(encoding="utf-8"))


def _resolver_step(context: str) -> dict:
    steps = [
        step
        for path in sorted(_WORKFLOWS_DIR.glob("*.yml"))
        for job in yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs", {}).values()
        if job.get("name") == context
        for step in job["steps"]
        if step.get("name") == "Read the queued PR (merge_group)"
    ]
    assert len(steps) == 1, f"{context!r}: {len(steps)} resolver steps"
    return steps[0]


def _resolve(expression: str, payload: dict) -> str:
    """One `${{ ... }}` expression against the payload. Only the forms the
    resolver steps use; anything else is a test failure, not a guess."""
    m = re.fullmatch(r"\$\{\{\s*([a-z_.]+)\s*\}\}", expression)
    assert m, f"not a single expression: {expression!r}"
    path = m.group(1)
    if path == "github.token":
        return "a-token"
    if path == "github.repository":
        return payload["repository"]["full_name"]
    assert path.startswith("github.event."), f"unsupported context {path!r}"
    value = payload
    for key in path.removeprefix("github.event.").split("."):
        value = value[key]  # KeyError: the workflow names a field the payload lacks
    assert isinstance(value, str), (path, value)
    return value


def _argv(context: str, payload: dict, tmp_path: pathlib.Path) -> list[str]:
    step = _resolver_step(context)
    env = {name: _resolve(expr, payload) for name, expr in step["env"].items()}
    words = shlex.split(step["run"])
    assert words[:3] == ["python", "-m", "scripts.merge_group_pr"], words[:3]
    argv = ["merge_group_pr.py"]
    for word in words[3:]:
        if word.startswith("$"):
            word = env[word[1:]]
        elif word.startswith(_WORKFLOW_TMP):
            word = str(tmp_path / word.removeprefix(_WORKFLOW_TMP))
        argv.append(word)
    return argv


def _fake_gh(prs: dict[int, dict]):
    calls: list[tuple[str, ...]] = []

    def gh(*args: str) -> str:
        calls.append(args)
        if args[:2] == ("pr", "view"):
            number = int(args[2])
        else:
            number = int(args[-1].split("/pulls/")[1].split("/")[0].split("?")[0])
        if number not in prs:
            # What `_gh` raises when `gh` exits non-zero on a 404.
            raise RuntimeError(f"gh {' '.join(args)} failed: HTTP 404: Not Found")
        pr = prs[number]
        if args[:2] == ("pr", "view"):
            return ""
        if "/files" in args[-1]:
            return json.dumps([[{"filename": "apps/api/app/x.py"}]])
        if "/commits" in args[-1]:
            return json.dumps([[{"commit": {"message": "the queued change"}}]])
        return json.dumps(pr)

    return gh, calls


def _fake_git(payload: dict, pr_head_tree: str):
    group = payload["merge_group"]
    calls: list[tuple[str, ...]] = []

    def git(*args: str) -> tuple[int, str]:
        calls.append(args)
        if args[:2] == ("cat-file", "-e"):
            return 0, ""
        if args[:2] == ("merge-tree", "--write-tree"):
            assert args[2:] == (group["base_sha"], _PR_HEAD), args
            return 0, f"{pr_head_tree}\n"
        if args[0] == "rev-parse":
            assert args[1] == f"{group['head_sha']}^{{tree}}", args
            return 0, f"{_TREE}\n"
        raise AssertionError(args)

    return git, calls


def _pr(number: int) -> dict:
    return {
        "number": number,
        "title": "Update README.md",
        "body": "## Adversarial audit\nFindings: none\nDisposition: n/a\nScope: at cccccccc\n",
        "user": {"login": "Codertocat"},
        "head": {"sha": _PR_HEAD},
        "changed_files": 1,
        "commits": 1,
    }


@pytest.mark.unit
def test_the_derived_payloads_differ_only_in_the_ref() -> None:
    recorded = _payload(_RECORDED)
    for name in ("unparseable_ref.json", "no_such_pr.json"):
        derived = _payload(name)
        assert derived["merge_group"]["head_ref"] != recorded["merge_group"]["head_ref"]
        derived["merge_group"]["head_ref"] = recorded["merge_group"]["head_ref"]
        assert derived == recorded, f"{name} differs from the recorded payload beyond head_ref"


@pytest.mark.unit
def test_the_recorded_payload_has_the_fields_the_workflows_read() -> None:
    group = _payload(_RECORDED)["merge_group"]
    assert _payload(_RECORDED)["action"] == "checks_requested"
    for field in ("head_sha", "head_ref", "base_sha", "base_ref", "head_commit"):
        assert field in group, field


@pytest.mark.unit
@pytest.mark.parametrize("context", _JOBS)
def test_the_recorded_payload_resolves_to_its_pr(context, tmp_path, monkeypatch) -> None:
    payload = _payload(_RECORDED)
    gh, gh_calls = _fake_gh({104: _pr(104)})
    git, git_calls = _fake_git(payload, _TREE)
    monkeypatch.setattr(resolver, "_gh", gh)
    monkeypatch.setattr(resolver, "_git", git)
    argv = _argv(context, payload, tmp_path)

    assert resolver.main(argv) == 0

    assert ("api", "repos/octo-org/octo-repo/pulls/104") in gh_calls, gh_calls
    assert any(c[0] == "merge-tree" for c in git_calls), "the head was not checked"
    written = sorted(p.name for p in tmp_path.iterdir())
    assert written, "the step wrote nothing"
    body_file = "body.md" if context == "Adversarial audit recorded" else "pr_body.txt"
    assert (tmp_path / body_file).read_text(encoding="utf-8") == _pr(104)["body"]


@pytest.mark.unit
@pytest.mark.parametrize("context", _JOBS)
def test_the_recorded_payload_with_a_moved_pr_head_is_refused(
    context, tmp_path, monkeypatch
) -> None:
    """Same payload, but PR 104's head now merges to a different tree: it was
    pushed after the group was built."""
    payload = _payload(_RECORDED)
    gh, _ = _fake_gh({104: _pr(104)})
    git, _ = _fake_git(payload, "f" * 40)
    monkeypatch.setattr(resolver, "_gh", gh)
    monkeypatch.setattr(resolver, "_git", git)

    assert resolver.main(_argv(context, payload, tmp_path)) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
@pytest.mark.parametrize("context", _JOBS)
def test_an_unparseable_ref_is_refused_before_any_fetch(context, tmp_path, monkeypatch) -> None:
    payload = _payload("unparseable_ref.json")
    gh, gh_calls = _fake_gh({104: _pr(104)})
    git, git_calls = _fake_git(payload, _TREE)
    monkeypatch.setattr(resolver, "_gh", gh)
    monkeypatch.setattr(resolver, "_git", git)

    assert resolver.main(_argv(context, payload, tmp_path)) == 2
    assert gh_calls == [] and git_calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
@pytest.mark.parametrize("context", _JOBS)
def test_a_ref_naming_a_pr_that_does_not_exist_is_refused(context, tmp_path, monkeypatch) -> None:
    payload = _payload("no_such_pr.json")
    gh, gh_calls = _fake_gh({104: _pr(104)})
    git, git_calls = _fake_git(payload, _TREE)
    monkeypatch.setattr(resolver, "_gh", gh)
    monkeypatch.setattr(resolver, "_git", git)

    assert resolver.main(_argv(context, payload, tmp_path)) == 2
    assert gh_calls and "pulls/999999" in gh_calls[0][-1], gh_calls
    assert git_calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_a_misspelt_payload_field_is_a_failure_here() -> None:
    """The point of resolving the workflow's expressions in this file: GitHub
    turns an unknown field into an empty string; this turns it into an error."""
    with pytest.raises(KeyError):
        _resolve("${{ github.event.merge_group.headref }}", _payload(_RECORDED))
