# -*- coding: utf-8 -*-
"""作业：列出题目与提交答案。

agent 负责推理答案；本模块只提供题目数据与提交通道。
填空题当前跳过（见 data.skipped）。
"""

import json

from .answers import parse_answers, read_answers  # noqa: F401 - 对外复用
from .chapters import LEAF_HOMEWORK, leaves_of_type
from .decrypt import Decryptor
from .http import ensure_data
from .output import log


def build_problem(problem):
    """把原始 problem 转成给 agent 的题目数据。

    返回 (problem_dict, skipped_dict)，二者恰有一个非 None。
    """
    problem_id = problem.get("problem_id")
    content = problem.get("content") or {}
    problem_type = content.get("Type")

    if problem_type == "FillBlank":
        return None, {"problem_id": problem_id, "reason": "FillBlank"}

    user = problem.get("user") or {}
    count = user.get("count")
    my_count = user.get("my_count") or 0
    if count:
        attempts_left = max(int(count) - int(my_count), 0)
        can_attempt = attempts_left > 0
    else:  # 0 / None 视为不限次数
        attempts_left = None
        can_attempt = True

    options = [
        {"key": option.get("key"), "value": option.get("value")}
        for option in content.get("Options", [])
    ]
    return (
        {
            "problem_id": problem_id,
            "type": problem_type,
            "body": content.get("Body"),
            "options": options,
            "attempts_left": attempts_left,
            "can_attempt": can_attempt,
        },
        None,
    )


def _fetch_exercise(context, homework_leaf):
    """返回 (exercise_id, exercise_data) 或 None。"""
    leaf_id_url = (
        f"https://{context.domain}/mooc-api/v1/lms/learn/leaf_info/"
        f"{homework_leaf['classroom_id']}/{homework_leaf['id']}/?term=latest"
        f"&uv_id={context.university_id}"
    )
    try:
        payload = context.session.json(context.session.get(leaf_id_url))
        exercise_id = payload["data"]["content_info"]["leaf_type_id"]
    except (KeyError, TypeError, ValueError):
        log(f"跳过作业 {homework_leaf.get('name')}：无法获取 leaf_type_id")
        return None

    exercise_url = (
        f"https://{context.domain}/mooc-api/v1/lms/exercise/get_exercise_list/"
        f"{exercise_id}/?term=latest&uv_id={context.university_id}"
    )
    response = context.session.get(exercise_url)
    payload = context.session.json(response)
    data = ensure_data(payload, "获取作业题目失败")
    font = data.get("font")

    if font:
        decrypted = Decryptor(context.session).get_encrypt_string(response.text, font)
        payload = json.loads(decrypted)
        data = payload["data"]

    return exercise_id, data


def collect_problems(context, course):
    """遍历课程下所有作业，返回 {exercises, skipped}。"""
    exercises = []
    skipped = []
    leaves = leaves_of_type(context, course, LEAF_HOMEWORK)
    for leaf in leaves:
        leaf = dict(leaf, classroom_id=course["classroom_id"])
        fetched = _fetch_exercise(context, leaf)
        if not fetched:
            continue
        exercise_id, data = fetched
        problems = []
        for problem in data.get("problems", []):
            info, skip = build_problem(problem)
            if skip:
                skipped.append(skip)
                continue
            problems.append(info)
        exercises.append(
            {
                "homework_id": leaf["id"],
                "exercise_id": exercise_id,
                "name": data.get("name"),
                "problems": problems,
            }
        )
    return {"exercises": exercises, "skipped": skipped}


def list_homework(context, course):
    collected = collect_problems(context, course)
    for item in collected["skipped"]:
        log(f"跳过填空题 problem_id={item['problem_id']}（暂不支持）")
    return {
        "course": {
            "classroom_id": course["classroom_id"],
            "course_name": course["course_name"],
        },
        "exercises": collected["exercises"],
        "skipped": collected["skipped"],
    }


def submit_homework(context, course, answers):
    collected = collect_problems(context, course)
    by_id = {}
    for exercise in collected["exercises"]:
        for problem in exercise["problems"]:
            by_id[str(problem["problem_id"])] = problem

    submit_url = (
        f"https://{context.domain}/mooc-api/v1/lms/exercise/problem_apply/"
        f"?term=latest&uv_id={context.university_id}"
    )
    results = []
    for answer in answers:
        problem_id = answer["problem_id"]
        problem = by_id.get(str(problem_id))
        if problem is None:
            results.append(
                {"problem_id": problem_id, "status": "skipped", "message": "题目不存在或填空题"}
            )
            continue
        if not problem["can_attempt"]:
            results.append(
                {"problem_id": problem_id, "status": "skipped", "message": "已达做题上限"}
            )
            continue

        body = {
            "classroom_id": course["classroom_id"],
            "problem_id": problem_id,
            "answer": answer["answer"],
        }
        response = context.session.post(submit_url, json=body)
        payload = context.session.json(response)
        if isinstance(payload, dict) and payload.get("data") is not None:
            results.append(
                {
                    "problem_id": problem_id,
                    "status": "ok",
                    "score": payload["data"].get("my_score"),
                    "message": payload.get("msg", ""),
                }
            )
        else:
            message = ""
            if isinstance(payload, dict):
                message = payload.get("msg") or payload.get("detail") or ""
            results.append(
                {"problem_id": problem_id, "status": "failed", "message": str(message)}
            )

    summary = {
        "total": len(results),
        "ok": sum(1 for item in results if item["status"] == "ok"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
    }
    return {"results": results, "summary": summary}
