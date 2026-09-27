# -*- coding: utf-8 -*-
"""stdout 统一 JSON 信封 / stderr 日志。

契约：
    成功  {"ok": true,  "data": ...}
    失败  {"ok": false, "error": {"code": ..., "message": ...}}
只有 stdout 用于数据交换；一切进度、提示都走 stderr。
"""

import json
import sys


def emit(data):
    """把成功结果以单个 JSON 信封写到 stdout。"""
    sys.stdout.write(json.dumps({"ok": True, "data": data}, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def emit_error(err):
    """把错误以 JSON 信封写到 stdout。"""
    payload = {
        "ok": False,
        "error": {
            "code": getattr(err, "code", "INTERNAL"),
            "message": str(err),
        },
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def log(message=""):
    """面向人的进度/提示，一律走 stderr。"""
    print(message, file=sys.stderr, flush=True)
