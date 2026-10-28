# 平台能力矩阵

核对日期：2026-10-28。只基于下列官方文档及本仓库测试，不推断未测版本兼容性。状态指**本项目交付的证据**，不是所有平台版本的普遍保证。

- **Enforced**：已在注明的真实宿主路径上观察到执行前拦截；前提是 Hook 受信、被调用且正常返回。不是不可绕过或全链路 fail-closed 的保证。
- **Advisory**：文本行为指导，不能形成执行边界。
- **Audit-only**：记录/事后观察，不阻止副作用。
- **Unsupported**：指定平台事件缺少所需能力，或本轮未实现该功能。
- **Unverified**：官方有能力或实现已有契约测试，但缺少真实宿主验证。

下表的 Enforced 证据来自已测的 v1 PROTECT 或 v2 Adaptive 指定路径；Codex 实测版本为 macOS 上的 CLI 0.160.0 与 0.164.0-alpha.11.1。STRICT 的策略/契约有自动测试，未单独完成真实宿主模式验证。新 bundle 默认 Adaptive：已识别风险可拒绝，UNKNOWN 仅 Audit-only/abstain；Skill 是 Advisory，真正的系统执行边界仍由宿主 Sandbox / OS 权限提供。更换模式不消除外层 Hook fail-open。上下文来源的采用/排除结论见[调研记录](execution-context.md)。

| 能力 | Codex CLI 0.160.0、0.164.0-alpha.11.1 / macOS | Claude Code | Cursor |
|---|---|---|---|
| Skill 行为约束 | Advisory；项目级名称/描述发现已实测，完整加载/遵守效果 Unverified | Advisory；文件安装已测，发现/效果 Unverified | Advisory；文件安装已测，发现/效果 Unverified |
| Bash 执行前拒绝 | **Enforced**，Adaptive 实测绝对路径保护/敏感读/越界读写、external、destructive Git；工具覆盖有限 | **Unverified**，已实现 PreToolUse 契约 | **Unverified**，本轮无适配器 |
| 文件工具拦截 | **Enforced**，原生 apply_patch 多文件增改删移及 .env 写入拒绝；其他文件工具 Unverified | Unverified，Read/Write/Edit 路径契约已测 | Unverified，无实现 |
| Bash 实际执行目录 | **Unsupported**：两个已测版本均未传入可信 workdir；相对目标在 Adaptive 记录 UNKNOWN 并 abstain，不声称识别了实际目录 | Unverified，cwd 语义需实测 | Unverified |
| 未知工具 | Adaptive 对实际 get_goal canary 记录 UNKNOWN + abstain；其他工具覆盖 Unverified，不能视为保护 | Unverified，契约测试 | Unsupported，无实现 |
| 任意 MCP / 所有工具语义 | Unsupported，未知调用保守拒绝/审批 | Unsupported，未知调用保守拒绝/审批 | Unsupported，无实现 |
| REQUIRE_APPROVAL → 真正审批 | **Unsupported**（PreToolUse ask 不支持），转拒绝已实测 | **Unverified**，default 模式输出 ask；无自动批准 | preToolUse **Unsupported**（ask 不执行）；其他专用事件 Unverified |
| ALLOW 不主动授权 | 已实测空对象 abstain；宿主原限制完整性仍 Unverified | Unverified，空对象契约已测 | Unsupported，无实现 |
| 原生执行规则 | Unverified 执行；`execpolicy check` 真实语义验证通过 | Unverified 原生 permissions，安装器不改权限 | Unverified CLI permission tokens |
| Sandbox 文件/网络限制 | 原生提供；本项目边界完整性 Unverified | 原生提供，平台/工具限制见下；Unverified | 原生提供，见 Run Modes；Unverified |
| OBSERVE / Adaptive UNKNOWN 审计 | **Audit-only**，真实宿主已测 | Audit-only 实现；宿主 Unverified | Unsupported，无实现 |
| Hook 启动/崩溃/超时保障 | 宿主 fail-open 已实测；内部 worker 超时转拒绝已实测 | Unverified，生成 onFailure=block，要求 2.1.295+ | Unverified，官方 failClosed 可配置 |
| PostToolUse 回滚副作用 | Unsupported | Unsupported | Unsupported |

## Codex 官方依据

[Hooks](https://learn.chatgpt.com/docs/hooks)：配置层相邻 hooks.json 或 inline hooks；项目层须信任，非托管 Hook 当前定义需审查。平台文档列出 canonical Bash、apply_patch、MCP 和部分本地工具；托管工具、特殊路径和 write_stdin 后续输入存在覆盖缺口。PreToolUse deny 或 exit 2 可阻止执行；ask 未实现，异常/超时/坏输出可放行。PostToolUse 在副作用之后。测试范围与反例见[验证记录](verification.md)，不能从文档列出的工具推导本项目全覆盖。

本轮使用本地脚本化 provider 与内置 gpt-5.5 工具元数据，真实执行 structured exec_command / freeform apply_patch / get_goal，无远程推理。这个模型名称只选择宿主工具协议；code-mode、Responses lite 和其他模型工具路径仍 **Unverified**。在两个已测版本中，Bash 的 `tool_input` 都未向适配器提供可信的实际 workdir；事件 cwd 仍为会话目录，即使 exec_command.workdir 指向测试额外根目录。适配器不补猜这个丢失字段。

[Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)：原生 prefix_rule 按 argv 前缀匹配，冲突 forbidden > prompt > allow；主要控制沙箱外执行路径。不要将若干前缀规则当完整 Shell 或路径策略。本项目不添加 allow 规则。

[配置优先级](https://learn.chatgpt.com/docs/config-file/config-basic)：CLI > 受信项目层（近目录优先）> profile > 用户 > 云默认 > 系统 > 内置；强制 requirements 约束另计。Hook 来源是累加，不简单按普通配置覆盖。安装器不修改这些全局层。

[审批和沙箱](https://learn.chatgpt.com/docs/agent-approvals-security)：Sandbox 与 approval policy 是独立层；文件、网络和工具范围依执行环境而异。应保持原有限制，不能用 Hook 取代内核边界。

[Skill 发现](https://learn.chatgpt.com/docs/build-skills)：仓库从 cwd 向上扫描 .agents/skills，另有用户、管理员和内置来源。按需加载不是强制遵守。

## Claude Code 官方依据

[Hooks reference](https://code.claude.com/docs/en/hooks)：PreToolUse 接收 cwd/tool_name/tool_input/permission_mode 等，输出 hookSpecificOutput.permissionDecision。deny 拒绝、ask 请求宿主确认；本适配器不用 allow 授权。普通错误/超时默认不阻止；2.1.295+ 的 command/http Hook 可用 onFailure=block。成功 JSON 退出 0，exit 2 是阻止。生成配置使用新字段，旧版本不能当已支持。

[Permissions](https://code.claude.com/docs/en/permissions)：原生 deny > ask > allow；PreToolUse 不覆盖所有特殊路径，例如 EndConversation 不进入同样流程。应用实际版本的权限流，不把模拟 ask 当作用户已批准。

[Settings](https://code.claude.com/docs/en/settings)：managed > CLI settings > project local > shared project > user；列表有合并规则，原生权限 deny 优先不等同普通键优先级。配置变更需按宿主要求审查/重启。

[Sandbox](https://code.claude.com/docs/en/sandboxing)：OS 级 shell 边界覆盖其子进程；文件工具、MCP 和 Hook 不属于同一沙箱。支持 macOS/Linux/WSL2，原生 Windows 命令不具备该沙箱；默认关闭。本项目不会启停或放宽它。

[Skills](https://code.claude.com/docs/en/skills)：.claude/skills 支持项目、用户、企业等来源；同名 enterprise > personal > project，插件有命名空间。仓库信任、设置源和安全模式可影响实际加载。本轮未安装 Claude CLI，不声明已完成这些发现或审批验证。

## Cursor 官方依据

[Hooks](https://cursor.com/docs/hooks)：原生事件 preToolUse 与 beforeShellExecution 等不同；preToolUse 的 ask 字段虽被 schema 接受但不执行。exit 2 拒绝；普通崩溃/超时默认 fail-open，failClosed=true 可更保守；当前权限 Hook 文档说明无效 JSON 阻止。来源优先级 Enterprise > Team > Project > User。本轮未跑 Cursor，所有安装及失败效果均 Unverified。

[Skills](https://cursor.com/docs/skills)：支持 .agents/skills 与 .cursor/skills，兼容其他目录；远程/云同步范围不同。[Rules](https://cursor.com/docs/rules)：Team > Project > User 的文本规则是 Advisory，不是系统权限。

[Run Modes](https://cursor.com/docs/agent/security/run-modes)：沙箱和自动运行审批独立；sandbox.json 可配读写/网络范围，项目配置优先且受团队/内置约束。Read Access 依版本而异，macOS/Linux 有不同沙箱实现。

[CLI permissions](https://cursor.com/docs/cli/reference/permissions)：项目 cli.json / 用户 cli-config.json 提供 Shell/Read/Write/WebFetch/MCP tokens，deny 优先。[Agent Security](https://cursor.com/docs/agent/security)：审批和 workspace trust 各有适用范围，默认行为不等于不可绕过隔离。没有本轮真实结果支撑的范围均不升级为 Enforced。
