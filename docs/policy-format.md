# Policy format v1 / v2

校验实现以 `guardrails/policy.py` 为准：无 YAML、动态表达式或 eval。JSON 拒绝重复键、非有限数字、过深和超过 1 MiB 的输入。未知字段/类别、无效策略或输入均保守拒绝，不回显原文。

| 配置字段 | 类型和默认值 |
|---|---|
| version | 整数 1（遗留模式）或 2（Adaptive），必填 |
| mode | v1 为 OBSERVE / PROTECT / STRICT；v2 只能为 ADAPTIVE，必填 |
| workspace_root | 存在的绝对目录，不能为文件系统根，必填 |
| protected_paths | 路径数组，默认 .git/.codex/.claude/.cursor/.guardrails；相对根解析；替换数组需保留想继续保护的项 |
| sensitive_names | 精确路径组件数组，默认 .env/.ssh/.aws/credentials/id_rsa/id_ed25519；另外始终匹配 .env. 前缀组件；不是完整凭据识别器 |
| category_decisions | 敏感类别覆盖值，仅 DENY / REQUIRE_APPROVAL，不能设 ALLOW |
| development_commands | 完整 argv 数组，默认空；仅由受信配置预审 |
| rules | 至多 256 条规则，默认空 |

安装 CLI / install API 省略 mode 时生成 v2 ADAPTIVE。已有 v1 策略不重解释、不自动迁移；使用 `migrate` 才会创建独立 v2 bundle。遗留模式仍可显式选择。本轮不扩大 Shell 语法或 development_commands 允许列表。底层 `default_policy` 辅助函数仍默认构造 PROTECT，安装器显式传入 ADAPTIVE，不代表旧 API 的语义变化。

敏感类别：destructive_git、data_destruction、external、production、opaque_execution。默认均 REQUIRE_APPROVAL；STRICT 的 opaque_execution 为 DENY。

规则必填 id、priority、decision，及至少一个 kinds/categories/path_prefixes 选择器。ID 唯一，最多 64 个小写字母/数字/点/连字符/下划线，不以 system. 开头。priority 为 0–499 整数。decision 为 ALLOW / DENY / REQUIRE_APPROVAL。选择器间 AND，数组内 OR；路径按组件包含，docs 不匹配 docs-old。

## 优先级和冲突

最高数值优先级胜出，同级 DENY > REQUIRE_APPROVAL > ALLOW；同级同结果的全部 ID 排序返回。系统保护不能被普通 allow 规则抹除：

| 优先级 | 系统策略 |
|---|---|
| 900 | 敏感访问、保护资源修改及删除其祖先 |
| 800 | cwd 或显式目标在工作区外 |
| 700 | 未知操作：ADAPTIVE 记录 UNKNOWN 并 Hook abstain；PROTECT 审批、STRICT 拒绝 |
| 600 | 敏感操作类别 |
| 0–499 | 配置规则 |
| 0 | 常规 scoped 操作默认 ALLOW |

无效配置/输入直接 DENY。`UNKNOWN` 不是可配置规则 decision，也不是有效 CLI 执行许可；仅当 v2 ADAPTIVE 缺少可信分类时产生。其 Hook effective result 为空 abstain，不产生宿主授权。正常 OBSERVE 保留 policy_decision，只将 effective_decision 设为 ALLOW，不产生宿主授权。

## 结构化操作

```json
{"kind":"write","cwd":"/absolute/path/to/project","paths":["src/app.txt"],"categories":[],"argv":[]}
```

kind 必须为 read/write/delete/git/development/execute/external/production/unknown。JSON API 中 read/write/delete 必须有非空 paths。cwd 默认配置根。argv 只是元数据，不执行、不批准。类别只能增加风险，不能携带批准状态。通用 API 假设调用方可信，不能直接相信模型填写的 kind=read。

本机 Path.resolve 解析 `..` 和现有 symlink 后按组件判断；外来 OS 路径无法解释时拒绝。判断后路径可能变化，不替代内核权限。Shell 仅接受窄语法；组合、重定向、替换、转义、glob 和未知程序/参数进入 unknown，允许误拦截也不假装理解完整语义。

通用 API 的 cwd 是可信调用方提供的上下文，不意味着宿主总能提供实际工具目录。已测的 Codex 0.160.0 与 0.164.0-alpha.11.1 Bash 均没有向适配器传入可信实际 workdir；相对路径、无绝对 `-C` 的 Git 和依赖 cwd 的 development_commands 归为 unknown。精确 argv 不能补足缺失上下文或隐式授权。窄语法支持绝对 cat/touch/ls 参数及一个绝对 `git -C`；并未通用地允许 Git 全局参数或 Shell 组合。
