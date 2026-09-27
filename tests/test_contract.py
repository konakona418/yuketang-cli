# -*- coding: utf-8 -*-
"""契约测试：不需要真实账号或网络，外部调用一律 monkeypatch。"""

import json

import pytest

from yuketang_cli import cli
from yuketang_cli.answers import parse_answers, read_answers
from yuketang_cli.errors import AuthExpired, InvalidInput
from yuketang_cli.homework import build_problem
from yuketang_cli.output import emit, emit_error


# --------------------------------------------------------------------------- #
# 输出信封
# --------------------------------------------------------------------------- #
def test_success_envelope(capsys):
    emit({"a": 1})
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "data": {"a": 1}}


def test_error_envelope(capsys):
    emit_error(AuthExpired("登录过期"))
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": False,
        "error": {"code": "AUTH_EXPIRED", "message": "登录过期"},
    }


# --------------------------------------------------------------------------- #
# answers 解析
# --------------------------------------------------------------------------- #
def test_parse_answers_list():
    assert parse_answers([{"problem_id": 1, "answer": "A"}]) == [
        {"problem_id": 1, "answer": "A"}
    ]


def test_parse_answers_mapping():
    assert parse_answers({"1": "A", "2": "B, C"}) == [
        {"problem_id": "1", "answer": "A"},
        {"problem_id": "2", "answer": "B, C"},
    ]


def test_parse_answers_wrapped():
    payload = {"answers": [{"problem_id": 1, "answer": "A"}]}
    assert parse_answers(payload) == [{"problem_id": 1, "answer": "A"}]


def test_parse_answers_leaf_key():
    assert parse_answers([{"leaf_id": 9, "answer": "hi"}], id_key="leaf_id") == [
        {"leaf_id": 9, "answer": "hi"}
    ]


def test_parse_answers_invalid():
    with pytest.raises(InvalidInput):
        parse_answers("not a list")
    with pytest.raises(InvalidInput):
        parse_answers([{"problem_id": 1}])


def test_read_answers_stdin(monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO('[{"problem_id": 1, "answer": "A"}]'))
    assert read_answers("-") == [{"problem_id": 1, "answer": "A"}]


# --------------------------------------------------------------------------- #
# 题目构造
# --------------------------------------------------------------------------- #
def test_build_problem_skips_fillblank():
    problem = {
        "problem_id": 7,
        "content": {"Type": "FillBlank", "Body": "___"},
        "user": {"count": 1, "my_count": 0},
    }
    info, skip = build_problem(problem)
    assert info is None
    assert skip == {"problem_id": 7, "reason": "FillBlank"}


def test_build_problem_attempt_limit():
    problem = {
        "problem_id": 8,
        "content": {
            "Type": "MultipleChoice",
            "Body": "?",
            "Options": [{"key": "A", "value": "x"}],
        },
        "user": {"count": 2, "my_count": 2},
    }
    info, skip = build_problem(problem)
    assert skip is None
    assert info["attempts_left"] == 0
    assert info["can_attempt"] is False
    assert info["options"] == [{"key": "A", "value": "x"}]


def test_build_problem_unlimited():
    problem = {
        "problem_id": 9,
        "content": {"Type": "Judgement", "Body": "?"},
        "user": {"count": 0, "my_count": 0},
    }
    info, _ = build_problem(problem)
    assert info["attempts_left"] is None
    assert info["can_attempt"] is True


# --------------------------------------------------------------------------- #
# CLI 行为与退出码
# --------------------------------------------------------------------------- #
def test_missing_domain_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    code = cli.main(["courses"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["error"]["code"] == "INVALID_INPUT"


def test_missing_cookie_exit_3(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    code = cli.main(["courses", "--domain", "buu.yuketang.cn"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["error"]["code"] == "AUTH_EXPIRED"


def test_usage_error_exit_2():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["homework", "submit", "--all"])
    assert excinfo.value.code == 2


def test_mutually_exclusive_course_all():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["homework", "list", "--course", "1", "--all"])
    assert excinfo.value.code == 2


def test_submit_wiring(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps([{"problem_id": 1, "answer": "A"}]), encoding="utf-8"
    )

    course = {"classroom_id": 1, "course_name": "测试课"}
    monkeypatch.setattr(cli, "load_context", lambda args, need_user_id=False: object())
    monkeypatch.setattr(cli, "select_courses", lambda context, args: [course])

    captured = {}

    def fake_submit(context, course_, answers):
        captured["answers"] = answers
        return {"results": [], "summary": {"total": 0}}

    monkeypatch.setattr(cli, "submit_homework", fake_submit)

    code = cli.main(["homework", "submit", "--all", "--answers", str(answers_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert captured["answers"] == [{"problem_id": 1, "answer": "A"}]
    assert payload["ok"] is True
    assert payload["data"]["courses"][0]["course"]["classroom_id"] == 1


def test_submit_invalid_answers_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    answers_path = tmp_path / "bad.json"
    answers_path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(cli, "load_context", lambda args, need_user_id=False: object())
    monkeypatch.setattr(
        cli, "select_courses", lambda context, args: [{"classroom_id": 1, "course_name": "c"}]
    )
    code = cli.main(["homework", "submit", "--all", "--answers", str(answers_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["error"]["code"] == "INVALID_INPUT"
