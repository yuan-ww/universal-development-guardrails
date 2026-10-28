# 执行上下文调研与受限方案

核对日期：2026-10-28；已固定验证的 Codex CLI 为 0.160.0 与 0.164.0-alpha.11.1。结论：本轮未找到可直接用于 Bash 相对目标判定的、稳定且可信的逐工具执行目录来源。不因宿主版本变化猜测修复，不将未验证集成标为支持。

## 候选来源

| 来源 | 依据与处理 |
|---|---|
| 原始 exec_command.workdir | 真实工具接受，但已有 outside-cwd 控制组证明它未进入 canonical Bash Hook。工具收到它不等于 UDG 收到它；当前不可用 |
| Hook cwd / SessionStart / 启动 `-C` | [官方 Hooks](https://learn.chatgpt.com/docs/hooks)定义 cwd 为会话目录，Hook 自身也在会话目录运行；不是待执行工具目录。已测额外根目录操作可与它不同，不采用 |
| Hook 进程的 cwd / PWD / 父进程目录 | 不是待执行工具的可信上下文；探测不能证明绑定到当前调用，且有平台、环境和竞争问题，不采用 |
| transcript_path + tool_use_id | [官方 Hooks](https://learn.chatgpt.com/docs/hooks)明确 transcript 格式不是稳定 Hook 接口。历史/未落盘记录、调用关联和环境选择均缺乏可验证保证；不读取会话历史反推权限，也不引入敏感日志采集 |
| 命令内绝对路径 / 一个绝对 git -C | 已实现且真实验证，窄语法直接检查请求中的显式目标；不是可信实际 cwd、身份或批准凭证，也不能约束所有间接访问。保留现状，不扩大语法 |
| updatedInput / Shell 包装器 / 自填 workdir 或 approved | 不能提供缺失事实；改写会改变命令语义，Codex 更新输入还需要 allow 响应。本适配器不返回授权 allow，不以包装器或 Agent 自签字段绕过判断 |
| 原生执行规则与 Sandbox | [Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)的 argv 前缀不是路径上下文；[Sandbox/审批](https://learn.chatgpt.com/docs/agent-approvals-security)是独立执行边界。保留既有原生限制，不假称它们给 UDG 注入逐工具目录 |

以上区分官方契约、真实控制组证据与工程上“不采用”的判断；未对每一种被排除的推测机制实现实验或适配器。

## 可用性选择

1. 新安装默认 Adaptive：可信结构化上下文识别出的敏感文件、保护路径、越界目标和高风险类别仍拒绝或要求审批；缺失可信实际目录的相对调用记录 UNKNOWN 并 abstain。它没有把未知操作变成“已证实安全”，没有增加审批授权。
2. OBSERVE / PROTECT / STRICT 保留为 v1 兼容模式。相对文件目标、缺失可信执行目录的 Git / development_commands 和不透明命令不会由允许列表或归一化器猜测为安全。
3. 在确有语义等价需求时，操作者可使用已有窄语法支持的绝对目标或单个绝对 git -C；不要把测试/编译脚本改成包装命令来绕过策略，不据此宣称完整开发流程低误拦截。
4. 继续使用实际 Sandbox、系统权限和宿主审批控制风险。Adaptive UNKNOWN 的低干扰不能计为安全能力；已识别风险的拦截仍受外层 Hook fail-open 与覆盖缺口限制。

默认策略变更不迁移已有 bundle，不自动降级操作者选择的拦截模式。不新增启动包装器、私有目录协议、常驻监视器或跨平台抽象；没有可信上下文时，预览版停留在此受限方案。

重新考虑相对命令放行的前提应是宿主提供受支持、绑定当前调用及执行环境的实际目录；适配器还须验证路径解析、子代理/多根目录和无 Hook 对照。当前未满足，不承诺交付时间或继续堆积测试来替代能力。
