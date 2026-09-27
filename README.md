# yuketang-cli

雨课堂 CLI，**面向 coding agent**：stdout 只输出统一 JSON，进度走 stderr，退出码确定。

由 [yuketangHelperBUU](https://github.com/MuWinds/yuketangHelperBUU) 重构而来。与原项目最大的区别：
原项目由程序内置 LLM 答题、靠 `input()` 与人交互；本项目只负责「供题 + 提交 + 刷视频」，
**答题由调用它的 agent 自己完成**。

## 安装 / 运行

```bash
# 安装依赖（仓库内运行，不追求全局安装）
uv sync            # 或 pip install -e ".[dev]"

# 两种等价入口
uv run yt --help
python -m yuketang_cli --help
```

## 输出契约

- 成功：`{"ok": true, "data": ...}`
- 失败：`{"ok": false, "error": {"code": "...", "message": "..."}}`
- 退出码：`0` 成功 / `1` 失败 / `2` 用法或入参错误 / `3` 未认证或登录过期
- `error.code ∈ {AUTH_EXPIRED, NETWORK, REMOTE, INVALID_INPUT, NOT_FOUND, INTERNAL}`
- 一切进度、原文提示走 stderr；stdout 永远只有一个 JSON 对象
- 键/码/flag 英文，`message` 中文

## 命令

```bash
yt login  [--domain buu.yuketang.cn] [--cookie-file F | --cookie '...'] [--timeout 180]
yt courses
yt video list   --course <classroom_id> | --all
yt run          --course <classroom_id> | --all [--workers 4] [--rate 12] [--video ID ...]
yt homework list   --course <classroom_id> | --all
yt homework submit --course <classroom_id> | --all --answers <file|->
yt discuss  list   --course <classroom_id> | --all
yt discuss  submit --course <classroom_id> | --all --answers <file|->
```

- 课程一律用稳定的 `classroom_id` 指定（来自 `yt courses`），不依赖列表顺序。
- 凭据与域名持久化在 `~/.config/yuketang/`（遵循 `XDG_CONFIG_HOME`）：
  - `config.json`：域名、`university_id`
  - `cookies.json`：cookie
- 二维码登录时，二维码图片路径与扫码链接打印在 **stderr**，命令会阻塞到扫码成功或超时。

## Agent 典型工作流

```bash
yt login --domain buu.yuketang.cn        # 人扫码一次
yt courses                               # 拿到 classroom_id
yt homework list --course 12345          # 拿到题目 JSON（含 problem_id/type/options/attempts_left）
# agent 推理答案，写出 answers.json：
#   [{"problem_id": 111, "answer": "A"}, {"problem_id": 222, "answer": "B, C"}]
yt homework submit --course 12345 --answers answers.json
```

`answers.json` 也接受 `{"111": "A", "222": "B, C"}` 这种映射写法；`--answers -` 从 stdin 读取。

## 数据形状

`yt homework list --course N`：

```json
{"courses": [{"course": {"classroom_id": 1, "course_name": "..."},
  "exercises": [{"homework_id": 2, "exercise_id": 3, "name": "第一章作业",
    "problems": [{"problem_id": 111, "type": "MultipleChoice", "body": "...",
      "options": [{"key": "A", "value": "..."}],
      "attempts_left": 3, "can_attempt": true}]}],
  "skipped": [{"problem_id": 112, "reason": "FillBlank"}]}]}
```

`yt discuss list --course N`：

```json
{"courses": [{"course": {"classroom_id": 1, "course_name": "..."},
  "topics": [{"leaf_id": 9, "topic": "...", "finished": false}]}]}
```

## 当前范围

- 支持：课程、视频、选择题/判断题/简答题等非填空题的作业、讨论区。
- 跳过：填空题（`homework list` 放入 `skipped`，`submit` 忽略；见 `data.skipped`）。
- `yt run` 只刷视频，不含答题。
