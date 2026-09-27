# -*- coding: utf-8 -*-
"""answers 文件/stdin 的解析（作业用 problem_id，讨论用 leaf_id）。"""

import json
import sys

from .errors import InvalidInput


def parse_answers(payload, id_key="problem_id"):
    """规范成 [{id_key: ..., "answer": ...}]。

    接受两种形状：
        [{"problem_id": 123, "answer": "A"}, ...]
        {"123": "A", "456": "B"}
    也接受带 "answers" 外层键的对象。
    """
    if isinstance(payload, dict) and "answers" not in payload:
        return [{id_key: key, "answer": value} for key, value in payload.items()]
    if isinstance(payload, dict):
        payload = payload["answers"]
    if not isinstance(payload, list):
        raise InvalidInput("answers 必须是数组，或 {id: answer} 对象")

    answers = []
    for item in payload:
        if not isinstance(item, dict) or id_key not in item or "answer" not in item:
            raise InvalidInput(f"answers 每一项必须包含 {id_key} 和 answer")
        answers.append({id_key: item[id_key], "answer": item["answer"]})
    return answers


def read_answers(source, id_key="problem_id"):
    if source == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(source, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            raise InvalidInput(f"无法读取 answers 文件：{source}（{exc}）") from exc
    if not text.strip():
        raise InvalidInput("answers 内容为空")
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise InvalidInput(f"answers 不是合法 JSON：{exc}") from exc
    return parse_answers(payload, id_key)
