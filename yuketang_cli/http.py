# -*- coding: utf-8 -*-
"""统一 HTTP 客户端：集中处理超时重试、限流等待和 JSON 解析。

所有业务模块都通过 Session 发请求，避免重试/限流逻辑散落各处。
"""

import json
import re
import time

import requests

from .errors import AuthExpired, NetworkError, RemoteError
from .output import log

# 雨课堂限流响应示例：{"detail": "Request was throttled. Expected available in 1.0 second."}
_THROTTLE_RE = re.compile(r"Expected available in\s*(\d+\.?\d*)\s*seconds?\.", re.I)


class Session:
    def __init__(self, headers, max_retries=3, timeout=(3, 10)):
        self.headers = headers
        self.max_retries = max_retries
        self.timeout = timeout
        self._http = requests.Session()

    def request(self, method, url, max_retries=None, timeout=None, **kwargs):
        retries = self.max_retries if max_retries is None else max_retries
        attempt = 0
        while True:
            try:
                response = self._http.request(
                    method,
                    url,
                    headers=self.headers,
                    timeout=timeout or self.timeout,
                    **kwargs,
                )
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                attempt += 1
                if attempt >= retries:
                    raise NetworkError(
                        f"请求失败（{method} {url}），已重试 {retries} 次：{exc}"
                    ) from exc
                delay = 2 * attempt
                log(f"网络异常，{delay}s 后进行第 {attempt + 1} 次重试：{exc}")
                time.sleep(delay)
                continue

            delay = self._throttle_delay(response)
            if delay is not None:
                attempt += 1
                if attempt >= retries:
                    raise RemoteError(f"雨课堂持续限流，重试 {retries} 次仍失败：{url}")
                log(f"由于网络阻塞，万恶的雨课堂，等待 {delay + 1} 秒后重试…")
                time.sleep(delay + 1)
                continue

            return response

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    @staticmethod
    def _throttle_delay(response):
        text = response.text or ""
        if "Expected available in" not in text and response.status_code != 429:
            return None
        match = _THROTTLE_RE.search(text)
        if match:
            return float(match.group(1))
        return 1.0 if response.status_code == 429 else None

    @staticmethod
    def json(response):
        try:
            return json.loads(response.text)
        except ValueError as exc:
            raise RemoteError("雨课堂返回了非 JSON 响应") from exc


def ensure_data(payload, message):
    """取出业务响应中的 data；缺失时按内容判定是登录过期还是远端错误。"""
    if isinstance(payload, dict) and "data" in payload and payload["data"] is not None:
        return payload["data"]

    detail = ""
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("msg") or ""
    text = str(detail)
    lowered = text.lower()
    if any(token in lowered for token in ("login", "auth", "unauthor", "forbidden")) or any(
        token in text for token in ("登录", "认证", "过期")
    ):
        raise AuthExpired(f"{message}：登录已过期，请重新运行 yt login（{text}）")
    raise RemoteError(f"{message}：{text or payload}")
