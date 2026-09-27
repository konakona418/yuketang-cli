# -*- coding: utf-8 -*-
"""课程章节叶子节点的通用解析（视频/作业/讨论共用）。"""

from .http import ensure_data

LEAF_VIDEO = 0
LEAF_DISCUSSION = 4
LEAF_EXAM = 5
LEAF_HOMEWORK = 6


def fetch_leaves(context, course):
    url = (
        f"https://{context.domain}/mooc-api/v1/lms/learn/course/chapter"
        f"?cid={course['classroom_id']}&term=latest"
        f"&uv_id={context.university_id}&sign={course['course_sign']}"
    )
    payload = context.session.json(context.session.get(url))
    data = ensure_data(payload, "获取课程章节失败")

    leaves = []
    for chapter in data.get("course_chapter", []):
        for section in chapter.get("section_leaf_list", []):
            if "leaf_list" in section:
                leaves.extend(section["leaf_list"])
            else:
                leaves.append(section)
    return leaves


def leaves_of_type(context, course, leaf_type):
    return [leaf for leaf in fetch_leaves(context, course) if leaf.get("leaf_type") == leaf_type]
