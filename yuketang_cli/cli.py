# -*- coding: utf-8 -*-
"""yt 命令行入口。

面向 coding agent：stdout 单一 JSON 信封，进度走 stderr，退出码确定。
"""

import argparse
import sys

from . import __version__
from .answers import read_answers
from .auth import do_login, load_context
from .courses import list_courses, select_courses
from .discuss import list_discussions, submit_discussions
from .errors import YtError
from .homework import list_homework, submit_homework
from .output import emit, emit_error
from .video import list_videos, run_videos


def _add_common(parser):
    parser.add_argument("--domain", help="雨课堂域名，例如 buu.yuketang.cn")
    parser.add_argument("--cookie-file", help="cookie 文件路径（默认 ~/.config/yuketang/cookies.json）")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出更详细的日志")


def _add_course_args(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--course", help="classroom_id，见 yt courses")
    group.add_argument("--all", action="store_true", help="对所有课程执行")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="yt",
        description="雨课堂 CLI：供 coding agent 调用，输出统一 JSON。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # login
    login = subparsers.add_parser("login", help="扫码登录或导入 cookie")
    _add_common(login)
    login.add_argument("--cookie", help="直接传入 cookie 串或 JSON")
    login.add_argument("--timeout", type=float, default=180.0, help="扫码超时秒数，默认 180")
    login.set_defaults(func=_cmd_login)

    # courses
    courses = subparsers.add_parser("courses", help="列出账号下的课程")
    _add_common(courses)
    courses.set_defaults(func=_cmd_courses)

    # video list
    video = subparsers.add_parser("video", help="视频相关")
    video_sub = video.add_subparsers(dest="video_command", required=True)
    video_list = video_sub.add_parser("list", help="列出课程视频")
    _add_common(video_list)
    _add_course_args(video_list)
    video_list.set_defaults(func=_cmd_video_list)

    # run
    run = subparsers.add_parser("run", help="自动刷视频")
    _add_common(run)
    _add_course_args(run)
    run.add_argument("--workers", type=int, default=4, help="并发线程数，默认 4")
    run.add_argument("--rate", type=float, default=12, help="心跳进度步长，默认 12")
    run.add_argument("--video", nargs="*", default=None, help="只刷指定 video_id（可多个）")
    run.set_defaults(func=_cmd_run)

    # homework
    homework = subparsers.add_parser("homework", help="作业相关")
    homework_sub = homework.add_subparsers(dest="homework_command", required=True)
    homework_list = homework_sub.add_parser("list", help="列出题目")
    _add_common(homework_list)
    _add_course_args(homework_list)
    homework_list.set_defaults(func=_cmd_homework_list)
    homework_submit = homework_sub.add_parser("submit", help="提交答案")
    _add_common(homework_submit)
    _add_course_args(homework_submit)
    homework_submit.add_argument(
        "--answers", required=True, help="answers 文件路径，- 表示从 stdin 读取"
    )
    homework_submit.set_defaults(func=_cmd_homework_submit)

    # discuss
    discuss = subparsers.add_parser("discuss", help="讨论相关")
    discuss_sub = discuss.add_subparsers(dest="discuss_command", required=True)
    discuss_list = discuss_sub.add_parser("list", help="列出讨论帖")
    _add_common(discuss_list)
    _add_course_args(discuss_list)
    discuss_list.set_defaults(func=_cmd_discuss_list)
    discuss_submit = discuss_sub.add_parser("submit", help="提交讨论回复")
    _add_common(discuss_submit)
    _add_course_args(discuss_submit)
    discuss_submit.add_argument(
        "--answers", required=True, help="answers 文件路径，- 表示从 stdin 读取"
    )
    discuss_submit.set_defaults(func=_cmd_discuss_submit)

    return parser


# --------------------------------------------------------------------------- #
# 子命令实现
# --------------------------------------------------------------------------- #
def _cmd_login(args):
    return do_login(args)


def _cmd_courses(args):
    context = load_context(args)
    return {"courses": list_courses(context)}


def _cmd_video_list(args):
    context = load_context(args)
    return {
        "courses": [
            {
                "course": {
                    "classroom_id": course["classroom_id"],
                    "course_name": course["course_name"],
                },
                "videos": list_videos(context, course),
            }
            for course in select_courses(context, args)
        ]
    }


def _cmd_run(args):
    context = load_context(args, need_user_id=True)
    return run_videos(
        context,
        select_courses(context, args),
        workers=args.workers,
        rate=args.rate,
        video_ids=args.video,
    )


def _cmd_homework_list(args):
    context = load_context(args)
    return {
        "courses": [
            list_homework(context, course) for course in select_courses(context, args)
        ]
    }


def _cmd_homework_submit(args):
    context = load_context(args)
    answers = read_answers(args.answers)
    return {
        "courses": [
            {
                "course": {
                    "classroom_id": course["classroom_id"],
                    "course_name": course["course_name"],
                },
                **submit_homework(context, course, answers),
            }
            for course in select_courses(context, args)
        ]
    }


def _cmd_discuss_list(args):
    context = load_context(args)
    return {
        "courses": [
            list_discussions(context, course) for course in select_courses(context, args)
        ]
    }


def _cmd_discuss_submit(args):
    context = load_context(args)
    answers = read_answers(args.answers, id_key="leaf_id")
    return {
        "courses": [
            {
                "course": {
                    "classroom_id": course["classroom_id"],
                    "course_name": course["course_name"],
                },
                **submit_discussions(context, course, answers),
            }
            for course in select_courses(context, args)
        ]
    }


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = args.func(args)
    except YtError as exc:
        emit_error(exc)
        return exc.exit_code
    except KeyboardInterrupt:
        emit_error(YtError("已中断", code="INTERNAL"))
        return 1
    except Exception as exc:  # noqa: BLE001 - 兜底，避免向 agent 抛裸异常
        emit_error(YtError(f"内部错误：{exc}"))
        return 1
    emit(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
