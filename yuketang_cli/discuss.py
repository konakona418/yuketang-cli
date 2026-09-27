# -*- coding: utf-8 -*-
"""讨论区：列出讨论帖与提交回复。"""

import time

from .chapters import LEAF_DISCUSSION, leaves_of_type
from .decrypt import clean_string
from .http import ensure_data
from .output import log


def _leaf_info(context, classroom_id, leaf_id):
    url = (
        f"https://{context.domain}/mooc-api/v1/lms/learn/leaf_info/"
        f"{classroom_id}/{leaf_id}/?term=latest&uv_id={context.university_id}"
    )
    payload = context.session.json(context.session.get(url))
    return ensure_data(payload, f"获取讨论 {leaf_id} 信息失败")


def list_discussions(context, course):
    topics = []
    for leaf in leaves_of_type(context, course, LEAF_DISCUSSION):
        try:
            data = _leaf_info(context, course["classroom_id"], leaf["id"])
        except Exception as exc:  # noqa: BLE001 - 单条讨论失败不影响其它
            log(f"跳过讨论 {leaf.get('name')}：{exc}")
            continue
        topic = clean_string(data.get("content_info", {}).get("context", ""))
        topics.append(
            {
                "leaf_id": leaf["id"],
                "topic": topic,
                "finished": bool(data.get("finish")),
            }
        )
    for topic in topics:
        if topic["finished"]:
            log(f"讨论 {topic['leaf_id']} 已完成，跳过")
    return {
        "course": {
            "classroom_id": course["classroom_id"],
            "course_name": course["course_name"],
        },
        "topics": topics,
    }


def submit_discussions(context, course, answers):
    submit_url = (
        f"https://{context.domain}/v/discussion/v2/comment/"
        f"?term=latest&uv_id={context.university_id}"
    )
    results = []
    for answer in answers:
        leaf_id = answer["leaf_id"]
        text = answer["answer"]
        try:
            data = _leaf_info(context, course["classroom_id"], leaf_id)
        except Exception as exc:  # noqa: BLE001
            results.append({"leaf_id": leaf_id, "status": "failed", "message": str(exc)})
            continue

        if data.get("finish"):
            results.append({"leaf_id": leaf_id, "status": "skipped", "message": "已完成"})
            continue

        sku_id = data.get("sku_id")
        leaf_type_id = data.get("id")
        timestamp = int(time.time() * 1000)
        unit_url = (
            f"https://{context.domain}/v/discussion/v2/unit/discussion/"
            f"?_date={timestamp}&term=latest&classroom_id={course['classroom_id']}"
            f"&sku_id={sku_id}&leaf_id={leaf_type_id}&topic_type=4&channel=xt"
        )
        try:
            unit = ensure_data(
                context.session.json(context.session.get(unit_url)),
                f"获取讨论 {leaf_id} 帖子信息失败",
            )
            topic_id = unit["id"]
            to_user = unit["user_id"]
        except Exception as exc:  # noqa: BLE001
            results.append({"leaf_id": leaf_id, "status": "failed", "message": str(exc)})
            continue

        body = {
            "to_user": to_user,
            "topic_id": topic_id,
            "content": {"text": text, "upload_images": [], "accessory_list": []},
            "anchor": 0,
        }
        payload = context.session.json(context.session.post(submit_url, json=body))
        if isinstance(payload, dict) and payload.get("success"):
            title = ((payload.get("data") or {}).get("data") or {}).get("title", "")
            results.append(
                {"leaf_id": leaf_id, "status": "ok", "message": title or "已提交"}
            )
        else:
            message = ""
            if isinstance(payload, dict):
                message = payload.get("msg") or payload.get("detail") or payload
            else:
                message = payload
            results.append({"leaf_id": leaf_id, "status": "failed", "message": str(message)})

    summary = {
        "total": len(results),
        "ok": sum(1 for item in results if item["status"] == "ok"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
    }
    return {"results": results, "summary": summary}
