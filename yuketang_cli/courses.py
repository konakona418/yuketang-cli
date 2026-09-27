# -*- coding: utf-8 -*-
"""课程列表与课程选择器。"""

import json

from .errors import InvalidInput, NotFound
from .http import ensure_data


def list_courses(context):
    url = (
        f"https://{context.domain}/mooc-api/v1/lms/user/user-courses/"
        f"?status=1&page=1&no_page=1&term=latest&uv_id={context.university_id}"
    )
    payload = context.session.json(context.session.get(url))
    data = ensure_data(payload, "获取课程列表失败")

    courses = []
    for item in data.get("product_list", []):
        courses.append(
            {
                "course_name": item.get("course_name"),
                "classroom_id": item.get("classroom_id"),
                "course_sign": item.get("course_sign"),
                "sku_id": item.get("sku_id"),
                "course_id": item.get("course_id"),
            }
        )
    return courses


def select_courses(context, args):
    """按 --course <classroom_id> 或 --all 选出目标课程。"""
    courses = list_courses(context)
    if getattr(args, "all", False):
        if not courses:
            raise NotFound("账号下没有可选课程")
        return courses

    classroom_id = getattr(args, "course", None)
    if classroom_id is None:
        raise InvalidInput("请指定 --course <classroom_id> 或 --all")
    for course in courses:
        if str(course["classroom_id"]) == str(classroom_id):
            return [course]
    raise NotFound(f"未找到 classroom_id={classroom_id} 的课程")
