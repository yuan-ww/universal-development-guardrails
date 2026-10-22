# Universal Development Guardrails

**帮助 AI 编程 Agent 围绕用户目标完成开发任务：该自主完成的自主完成，不该扩大的不扩大，该验证的真实验证，完成后及时停止。**

这是一个与语言、框架无关的开发约束项目，面向实现、调试、重构、代码审查和多步骤仓库操作。它希望减少任务跑偏、无关修改、过度设计、反复请示、破坏已有工作、虚假验证和无效返工。

**当前状态：Engineering Preview，尚未正式发布。** 推荐先试用纯文本 Skill。策略引擎和 Hook 是可选的独立能力，不会因安装 Skill 而自动开启。

本版重点是多轮目标一致性、上下文连续性，以及避免过度执行工程规范。现有真实 A/B 尚未观察到明确的防跑偏增量收益，不能将这些指导视为已证明有效的保障。

## 希望 Agent 怎样工作？

例如，要求 Agent 修复一个 Bug 时，预期它会定位相关代码、完成必要修改和验证，而不是顺便重构整个模块。正常的读取、编码和测试可以在授权范围内自主完成；删除他人数据、生产变更、强制推送等高风险操作则需要具体授权。

Skill 重点指导以下行为：

- **对准目标：** 区分用户授权、Agent 建议和普通讨论；重复提及不等于批准，不把无关优化塞进任务。
- **恢复连续性：** 交接或上下文压缩后，根据相关记录恢复目标、用户决定、否决与延期事项及已验证进度；缺失历史不编造。
- **控制范围：** 保护未提交修改和并行工作，保留必要修复与验证，不把非阻塞问题或可选完善升级为交付条件。
- **保持自主：** 不为每个常规步骤反复请求批准，也不强制 TDD、固定流程或测试工具。
- **谨慎处理风险：** 根据影响、权限和可恢复性判断是否需要先征得同意。
- **真实验证、适时结束：** 不削弱测试来制造成功；失败时基于新证据调整，达到目标后停止。

这些规则见 [SKILL.md](SKILL.md)；高风险情形按需参考 [风险与授权边界](references/risk-boundaries.md)。Skill 不授予权限，也不会覆盖宿主指令或系统保护。

## 核心组成

| 部分 | 作用 | 边界 |
|---|---|---|
| **Skill（推荐先试）** | 用文本指导 Agent 的目标、范围、自主性、验证和停止条件 | **Advisory**：不拦截工具，不保证 Agent 遵守 |
| **Policy Engine（可独立使用）** | 用 Python 3.11+ 标准库，对可信调用方提供的结构化操作信息作确定性判断；返回 ALLOW、DENY 或 REQUIRE_APPROVAL、理由和策略 ID | 不依赖 LLM，也不自行执行文件操作；不能完整理解任意 Shell |
| **Hook（可选、需人工启用）** | 在已接入的宿主工具路径上使用策略决策，记录审计或尝试拒绝操作 | 受宿主版本、工具覆盖、信任配置与失败处理限制，不能代替 Sandbox |

运行时支持 **OBSERVE / PROTECT / STRICT** 三种模式。首次安装默认 OBSERVE（只观察），而且**生成运行时 bundle 不等于启用 Hook**。

## 安装

需要 Git 和 Python 3.11+。先获取并审阅源码，在仓库目录执行以下命令，把示例路径替换为**已存在的项目目录绝对路径**：

```sh
git clone --depth 1 https://github.com/yuan-ww/universal-development-guardrails.git
cd universal-development-guardrails
python3.11 -I guardrails/runner.py install-skill --workspace "/absolute/path/to/your-project"
python3.11 -I guardrails/runner.py verify-skill --workspace "/absolute/path/to/your-project"
```

默认安装至目标项目的 `.agents/skills/universal-development-guardrails/`，不会覆盖现有目录，也不会修改全局配置、授予信任或启用 Hook。

在目标项目启动 Codex，查看 `/skills`，**显式调用** `$universal-development-guardrails`；必要时重启并核对启动目录。安装或发现 Skill 不等于模型完整加载、遵守或获得工具拦截能力。

Claude Code 和 Cursor 可分别添加 `--agent claude`、`--agent cursor` 安装到项目的 `.claude/skills/`、`.cursor/skills/`；文件安装已有测试，但真实宿主发现与实际效果仍为 **Unverified**。校验、卸载时须使用相同的 `--agent` 参数。Windows 可用 `py -3.11` 或其他已安装的 Python 3.11+ 替换 `python3.11`。

完整安装与异常恢复步骤见[快速指南](docs/quickstart.md)。

## 可选：策略运行时与 Hook

**仅使用 Skill 不需要本节。** 如果还希望评估操作风险或测试 Hook 拦截，可在源码仓库目录执行：

```sh
python3.11 -I guardrails/runner.py install --workspace "/absolute/path/to/your-project"
python3.11 -I guardrails/runner.py verify-install --destination "/absolute/path/to/your-project/.guardrails/udg-bundle"
```

这只会生成默认 **OBSERVE** bundle，包含运行时代码、`policy.json`、Hook 配置片段和校验清单。**Hook 尚未启用，也不会额外阻断正常判定的操作。** 可以使用 `--destination` 指定新的目标目录。

项目内可写的 bundle 不是安全隔离。操作者仍需保护解释器、策略、运行时代码和父目录；安装失败或校验不通过时不要启用残留文件，也不要强行清理用户内容。

### 启用 Hook

**Codex：** 现有真实宿主证据限定于 CLI 0.160.0 的已测路径，不可推断其他版本和全部工具都受保护。

1. 备份项目的 `.codex/hooks.json`，将 bundle 内 `codex-hooks.json` 的 `hooks.PreToolUse` 条目**人工合并**，保留其他 Hook。
2. 审阅并信任项目配置层和 `/hooks` 中当前 Hook 定义，确认启用后重启；不要削弱原有 Sandbox 或审批要求。
3. 先在隔离项目验证 OBSERVE 审计；需要尝试拦截时，另行验证允许、拒绝及实际文件副作用。

**Claude Code：** 有适配器和契约测试，但真实宿主集成为 **Unverified**；不要将其当作已验证保护部署，条件与人工步骤见[验证指南](docs/verification.md#claude-code-人工集成)。**Cursor：** 当前没有本项目的 Hook 适配器。

### 选择运行模式

| 模式 | 正常判定时的行为 |
|---|---|
| **OBSERVE（默认）** | 记录策略结果，不额外阻断，也不绕过宿主原有限制；损坏输入或配置仍可能拒绝 |
| **PROTECT（显式启用）** | 拒绝已识别的保护资源、敏感文件和越界操作；高风险或未知操作要求审批，宿主不能对接审批时拒绝 |
| **STRICT（显式启用）** | 在 PROTECT 的基础上直接拒绝未知或不透明执行 |

如需评估 PROTECT，**另建新 bundle**，不要直接覆盖正在使用的安装：

```sh
python3.11 -I guardrails/runner.py install --workspace "/absolute/path/to/your-project" --destination "/absolute/path/to/udg-protect-bundle" --mode PROTECT
```

STRICT 使用 `--mode STRICT`。先备份现有配置和 bundle，再人工替换原 UDG Hook 条目、审查信任并验证；不要叠加两套 UDG Hook。需要恢复时换回原配置和 bundle。

### 不启用 Hook，单独评估策略

在源码仓库目录执行；`evaluate` 只计算拟议操作的决策，不执行该操作：

```sh
python3.11 -m guardrails validate --policy "/absolute/path/to/policy.json"
printf '%s' '{"kind":"write","paths":["src/app.txt"]}' | python3.11 -m guardrails evaluate --policy "/absolute/path/to/policy.json"
python3.11 -m guardrails --help
```

可从安装 bundle 的 `policy.json` 入手，详见[策略格式](docs/policy-format.md)。结构化上下文必须由可信调用方提供，不能将模型自报的参数视为授权。有效决策退出码：ALLOW=0、DENY=2、REQUIRE_APPROVAL=3；OBSERVE 保留策略判断，但不额外阻断有效操作。

## 停用、卸载与升级

先从宿主配置中移除本项目 Hook 条目及可选原生规则，保留其他配置；必要时恢复未被后续修改的备份并重启确认。随后按需执行：

```sh
python3.11 -I guardrails/runner.py uninstall --destination "/absolute/path/to/your-project/.guardrails/udg-bundle"
python3.11 -I guardrails/runner.py uninstall-skill --workspace "/absolute/path/to/your-project"
```

卸载会校验清单；遇到用户修改、额外文件或 symlink 会拒绝删除。先保存自定义内容，不要强制清理。审计目录和父目录保留。升级同样先备份、校验，再保守卸载重装或选择新目录，不静默覆盖。

## 限制

- **审批与覆盖有限：** Codex 的 REQUIRE_APPROVAL 在拦截模式下转为拒绝；Claude 真实审批未验证。未经过 Hook 的工具、子进程副作用和其他旁路不受本项目控制。
- **不是系统沙箱：** 路径检查存在竞态、硬链接和平台差异；无法抵御可修改自身 Hook/策略的同权限进程。文件与网络执行边界仍依赖宿主 Sandbox 和 OS 权限。
- **并发审计仍有已知锁冲突：** 并发写入 SQLite 时仍可能出现锁冲突。OBSERVE 审计失败提示；仍能运行的 PROTECT / STRICT Hook 拒绝。不要将审计或此预览版视为可靠安全隔离。

## 测试与进一步阅读

日常源码回归可执行：

```sh
python3.11 -m unittest discover -s tests -v
```

此外可阅读[快速安装、验证与卸载](docs/quickstart.md)、[架构](docs/architecture.md)、[安全模型](docs/security-model.md)及[验证方式与效果边界](docs/verification.md)。测试与脚本化真实宿主验证不能冒充真实模型收益或生产验证。


## 许可证

本项目采用 [MIT License](LICENSE)，版权所有 © 2026 yuan-ww。
允许按照许可证条款使用、修改、分发及商业使用；复制或分发软件的全部或重要部分时须保留版权及许可声明。
软件按“原样”提供，不提供担保。
