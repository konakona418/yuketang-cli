# -*- coding: utf-8 -*-
"""统一错误类型与退出码。

退出码约定：
    0  成功
    1  一般失败（网络 / 远端 / 内部）
    2  用法或入参错误（含 argparse 自身）
    3  未认证 / 登录过期
"""


class YtError(Exception):
    code = "INTERNAL"
    exit_code = 1

    def __init__(self, message, *, code=None, exit_code=None):
        super().__init__(message)
        if code is not None:
            self.code = code
        if exit_code is not None:
            self.exit_code = exit_code


class InvalidInput(YtError):
    """参数缺失或非法。"""

    code = "INVALID_INPUT"
    exit_code = 2


class AuthExpired(YtError):
    """未登录、cookie 缺失或已过期。"""

    code = "AUTH_EXPIRED"
    exit_code = 3


class NetworkError(YtError):
    """连接、超时等网络层失败。"""

    code = "NETWORK"
    exit_code = 1


class RemoteError(YtError):
    """雨课堂返回了非预期的业务响应。"""

    code = "REMOTE"
    exit_code = 1


class NotFound(YtError):
    """目标资源（课程、题目等）不存在。"""

    code = "NOT_FOUND"
    exit_code = 1
