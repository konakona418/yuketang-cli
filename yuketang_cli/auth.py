# -*- coding: utf-8 -*-
"""登录、cookie / 域名持久化，以及请求上下文的装配。

- 二维码登录：`yt login`
- 导入已有 cookie：`yt login --cookie-file x.json` 或 `yt login --cookie 'sessionid=...'`
- 持久化位置遵循 XDG：默认 ~/.config/yuketang/{config.json, cookies.json}
"""

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import qrcode
import requests
import websocket

from .errors import AuthExpired, InvalidInput, NetworkError, RemoteError
from .http import Session
from .output import log

APP_DIR = "yuketang"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/87.0.4280.67 Safari/537.36"
)


@dataclass
class Context:
    domain: str
    university_id: str
    cookies: dict
    headers: dict
    session: Session
    user_id: str = None


# --------------------------------------------------------------------------- #
# 路径与配置
# --------------------------------------------------------------------------- #
def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    directory = Path(base) / APP_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def config_path() -> Path:
    return config_dir() / "config.json"


def default_cookie_path() -> Path:
    return config_dir() / "cookies.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def save_config(config: dict) -> None:
    config_path().write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# cookie 解析 / 读写
# --------------------------------------------------------------------------- #
def parse_cookie_text(text: str) -> dict:
    """兼容多种 cookie 输入：JSON 对象、浏览器导出的列表、原始 cookie 串。"""
    text = (text or "").strip()
    if not text:
        return {}

    try:
        obj = json.loads(text)
    except ValueError:
        obj = None

    if isinstance(obj, dict):
        if isinstance(obj.get("cookies"), list):
            obj = obj["cookies"]
        elif all(isinstance(value, str) for value in obj.values()):
            return {str(key): value for key, value in obj.items()}

    if isinstance(obj, list):
        cookies = {}
        for item in obj:
            if isinstance(item, dict) and item.get("name"):
                cookies[item["name"]] = item.get("value", "")
        return cookies

    cookies = {}
    for part in text.replace("\n", ";").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def load_cookies(explicit_path=None) -> dict:
    path = Path(explicit_path) if explicit_path else default_cookie_path()
    if not path.exists():
        raise AuthExpired(f"未找到 cookie 文件：{path}，请先运行 yt login")
    cookies = parse_cookie_text(path.read_text(encoding="utf-8"))
    if not cookies.get("sessionid"):
        raise AuthExpired(f"cookie 文件 {path} 缺少 sessionid，请重新运行 yt login")
    return cookies


def save_cookies(cookies: dict, explicit_path=None) -> Path:
    path = Path(explicit_path) if explicit_path else default_cookie_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


# --------------------------------------------------------------------------- #
# 头部与基础信息
# --------------------------------------------------------------------------- #
def build_headers(cookies: dict, university_id) -> dict:
    cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
    return {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Cookie": cookie_header,
        "x-csrftoken": cookies.get("csrftoken", ""),
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "university-id": str(university_id),
        "xtbz": "cloud",
    }


def fetch_university_id(domain: str) -> str:
    url = (
        f"https://{domain}/edu_admin/get_custom_university_info/"
        f"?current=1&_={int(time.time() * 1000)}"
    )
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=10,
        )
        return str(response.json()["data"]["university_id"])
    except (KeyError, TypeError, ValueError, requests.exceptions.RequestException) as exc:
        raise RemoteError(f"无法获取 university_id：{exc}") from exc


def fetch_user_id(session: Session, domain: str) -> str:
    response = session.get(f"https://{domain}/edu_admin/check_user_session/")
    match = re.search(r'"user_id":(.+?)}', response.text)
    if not match:
        raise AuthExpired("无法获取 user_id，cookie 可能已过期，请重新运行 yt login")
    return match.group(1).strip()


# --------------------------------------------------------------------------- #
# 二维码登录
# --------------------------------------------------------------------------- #
def _write_qr_png(url: str) -> Path:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    path = config_dir() / "qrcode.png"
    qr.make_image(fill_color="black", back_color="white").save(path, format="PNG")
    return path


def qr_login(domain: str, timeout: float = 180.0) -> str:
    """连 WebSocket 拿二维码，阻塞直到扫码成功或超时。返回 loginsuccess 的原始消息。"""
    holder = {"message": None}
    done = threading.Event()
    ws_holder = {}

    def request_qrcode(ws):
        ws.send(
            json.dumps(
                {"op": "requestlogin", "role": "web", "version": 1.4, "type": "qrcode"}
            )
        )

    def on_message(ws, message):
        msg = json.loads(message)
        if msg.get("ticket") and msg.get("qrcode"):
            url = msg["qrcode"]
            try:
                path = _write_qr_png(url)
            except Exception as exc:  # noqa: BLE001 - 二维码生成失败不应中断登录
                path = f"(生成失败: {exc})"
            log("请使用微信扫描二维码登录雨课堂：")
            log(f"  二维码图片：{path}")
            log(f"  扫码链接：{url}")
        if msg.get("op") == "requestlogin":
            request_qrcode(ws)
        if msg.get("op") == "loginsuccess":
            holder["message"] = message
            done.set()
            ws.close()

    def on_open(ws):
        request_qrcode(ws)

    ws = websocket.WebSocketApp(
        f"wss://{domain}/wsapp/",
        on_message=on_message,
        on_error=lambda _ws, error: log(f"登录 WebSocket 错误：{error}"),
        on_close=lambda *_a: done.set(),
    )
    ws.on_open = on_open
    ws_holder["ws"] = ws

    thread = threading.Thread(target=ws.run_forever, daemon=True)
    thread.start()

    if not done.wait(timeout):
        ws.close()
        raise NetworkError(f"扫码登录超时（{int(timeout)} 秒），请重试")
    if not holder["message"]:
        raise AuthExpired("登录未完成：WebSocket 在扫码成功前关闭")
    return holder["message"]


def verify_origin(domain: str, auth_info, user_id) -> dict:
    """扫码成功后向雨课堂换取正式 cookie。"""
    university_id = fetch_university_id(domain)
    url = (
        f"https://{domain}/edu_admin/account/login/verify-origin-system-bind"
        f"?term=latest&uv_id={university_id}"
    )
    headers = {
        "referer": f"https://{domain}/pro/portal/home/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Cookie": f"university_id={university_id};platform_id=3;xtbz=cloud;platform_type=1;",
        "Origin": f"https://{domain}",
        "Platform-Id": "3",
        "University-Id": str(university_id),
        "Terminal-Type": "web",
        "X-Client": "web",
        "X-Csrftoken": "undefined",
        "Xtbz": "cloud",
    }
    session = requests.Session()
    session.post(
        url,
        json={"auth": auth_info, "origin_user_id": str(user_id)},
        headers=headers,
        timeout=10,
    )
    cookies = requests.utils.dict_from_cookiejar(session.cookies)
    if not cookies.get("sessionid"):
        raise AuthExpired("登录验证未返回 sessionid，请重试")
    return cookies


# --------------------------------------------------------------------------- #
# 命令入口辅助
# --------------------------------------------------------------------------- #
def resolve_domain(args) -> str:
    domain = getattr(args, "domain", None) or load_config().get("domain")
    if not domain:
        raise InvalidInput(
            "未配置域名，请先运行 yt login --domain <域名>（例如 buu.yuketang.cn），"
            "或在命令上传 --domain"
        )
    return domain


def load_context(args, need_user_id=False) -> Context:
    config = load_config()
    domain = resolve_domain(args)
    cookies = load_cookies(getattr(args, "cookie_file", None))

    university_id = config.get("university_id") if config.get("domain") == domain else None
    if not university_id:
        university_id = fetch_university_id(domain)
        config["domain"] = domain
        config["university_id"] = university_id
        save_config(config)

    headers = build_headers(cookies, university_id)
    session = Session(headers)
    context = Context(
        domain=domain,
        university_id=university_id,
        cookies=cookies,
        headers=headers,
        session=session,
        user_id=None,
    )
    if need_user_id:
        context.user_id = fetch_user_id(session, domain)
    return context


def do_login(args) -> dict:
    config = load_config()
    domain = getattr(args, "domain", None) or config.get("domain")
    if not domain:
        raise InvalidInput("请通过 --domain 指定雨课堂域名，例如 buu.yuketang.cn")

    if args.cookie or args.cookie_file:
        if args.cookie:
            cookies = parse_cookie_text(args.cookie)
        else:
            path = Path(args.cookie_file)
            if not path.exists():
                raise InvalidInput(f"cookie 文件不存在：{path}")
            cookies = parse_cookie_text(path.read_text(encoding="utf-8"))
        if not cookies.get("sessionid"):
            raise AuthExpired("导入的 cookie 中缺少 sessionid")
    else:
        message = qr_login(domain, timeout=args.timeout)
        payload = json.loads(message)
        cookies = verify_origin(domain, payload["Auth"], payload["UserID"])

    university_id = fetch_university_id(domain)
    session = Session(build_headers(cookies, university_id))
    user_id = fetch_user_id(session, domain)

    cookie_path = save_cookies(cookies, getattr(args, "cookie_file", None))
    config["domain"] = domain
    config["university_id"] = university_id
    save_config(config)

    log(f"登录成功，cookie 已保存到 {cookie_path}")
    return {
        "domain": domain,
        "user_id": user_id,
        "university_id": university_id,
        "cookie_file": str(cookie_path),
    }
