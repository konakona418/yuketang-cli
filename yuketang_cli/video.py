# -*- coding: utf-8 -*-
"""视频观看：列表与自动刷课。"""

import json
import random
import re
import threading
import time

from .chapters import LEAF_VIDEO, leaves_of_type
from .output import log

HEARTBEAT_INTERVAL = 2


def list_videos(context, course):
    return [
        {"video_id": str(leaf["id"]), "name": leaf.get("name")}
        for leaf in leaves_of_type(context, course, LEAF_VIDEO)
    ]


def _progress_url(context, course, video_id, user_id):
    return (
        f"https://{context.domain}/video-log/get_video_watch_progress/"
        f"?cid={course['course_id']}&user_id={user_id}"
        f"&classroom_id={course['classroom_id']}&video_type=video&vtype=rate"
        f"&video_id={video_id}&snapshot=1&term=latest&uv_id={context.university_id}"
    )


def _watch_one(context, course, video_id, name, rate):
    """刷单个视频。返回 completed / skipped / failed。"""
    video_id = str(video_id)
    classroom_id = str(course["classroom_id"])
    user_id = str(context.user_id)
    heartbeat_url = f"https://{context.domain}/video-log/heartbeat/"
    progress_url = _progress_url(context, course, video_id, user_id)

    progress = context.session.get(progress_url)
    completed = "0"
    try:
        completed = re.search(r'"completed":(.+?),', progress.text).group(1)
    except AttributeError:
        pass
    if completed == "1":
        log(f"{name} 已经学习完毕，跳过")
        return "skipped"

    video_frame = 0
    value = 0
    try:
        payload = json.loads(progress.text)
        rate_value = payload["data"][video_id]["rate"]
        if rate_value is None:
            return "failed"
        value = rate_value
        video_frame = payload["data"][video_id]["watch_length"]
    except (KeyError, TypeError, ValueError):
        pass

    log(f"{name} 尚未学习，开始自动学习")
    timestamp = int(round(time.time() * 1000))

    while float(value) <= 0.95:
        heart_data = []
        for index in range(3):
            heart_data.append(
                {
                    "i": 5,
                    "et": "loadeddata",
                    "p": "web",
                    "n": "ali-cdn.xuetangx.com",
                    "lob": "cloud4",
                    "cp": video_frame,
                    "fp": 0,
                    "tp": 0,
                    "sp": 2,
                    "ts": str(timestamp),
                    "u": int(user_id),
                    "uip": "",
                    "c": course["course_id"],
                    "v": int(video_id),
                    "skuid": course["sku_id"],
                    "classroomid": classroom_id,
                    "cc": video_id,
                    "d": 4976.5,
                    "pg": video_id
                    + "_"
                    + "".join(random.sample("zyxwvutsrqponmlkjihgfedcba1234567890", 4)),
                    "sq": index + 1,
                    "t": "video",
                }
            )
            video_frame += rate
        context.session.post(heartbeat_url, json={"heart_data": heart_data})

        try:
            progress = context.session.get(progress_url)
            payload = json.loads(progress.text)
            rate_value = payload["data"][video_id]["rate"]
            if rate_value is None:
                return "failed"
            value = str(rate_value)
            log(f"{name} 学习进度：{format(float(value) * 100, '.2f')}%")
            time.sleep(HEARTBEAT_INTERVAL)
        except (KeyError, TypeError, ValueError) as exc:
            log(f"{name} 进度读取失败：{exc}")

    log(f"{name} 学习完成")
    return "completed"


def run_videos(context, courses, workers=4, rate=12, video_ids=None):
    """并发刷课。返回 {"videos": [...], "completed": n}。"""
    selected = {str(item) for item in video_ids} if video_ids else None
    results = []
    lock = threading.Lock()

    def worker(course, videos):
        for video in videos:
            if selected is not None and video["video_id"] not in selected:
                continue
            try:
                status = _watch_one(context, course, video["video_id"], video["name"], rate)
            except Exception as exc:  # noqa: BLE001 - 单个视频失败不应中断整批
                log(f"{video['name']} 处理失败：{exc}")
                status = "failed"
            with lock:
                results.append(
                    {
                        "course_name": course["course_name"],
                        "video_id": video["video_id"],
                        "name": video["name"],
                        "status": status,
                    }
                )

    for course in courses:
        videos = list_videos(context, course)
        log(f"{course['course_name']} 共 {len(videos)} 个视频")
        parts = [videos[index::workers] for index in range(workers)]
        threads = [
            threading.Thread(target=worker, args=(course, part)) for part in parts if part
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    completed = sum(1 for item in results if item["status"] == "completed")
    return {"videos": results, "completed": completed}
