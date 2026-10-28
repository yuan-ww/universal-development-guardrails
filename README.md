# Universal Development Guardrails

Universal Development Guardrails（UDG）为 AI 编程 Agent 提供目标、范围和风险控制能力：常规开发工作可在用户授权范围内自主推进；已识别的高风险操作保留必要的宿主审批或拒绝；完成目标后不继续扩展无关工作。

**当前状态：Engineering Preview，尚未正式发布。** UDG 由文本 Skill、确定性策略引擎和可选 Hook 组成。三者相互独立：安装 Skill 不会自动启用策略或 Hook，也不会改变宿主的 Sandbox、审批或全局配置。

## 功能

| 部分 | 提供的能力 | 作用边界 |
|---|---|---|
| **Skill** | 指导 Agent 识别用户目标、授权范围、已有工作、风险和完成条件 | 建议性约束；不拦截工具、不授予权限 |
| **Policy Engine** | 使用 Python 标准库对可信结构化操作信息作确定性决策：`ALLOW`、`DENY`、`REQUIRE_APPROVAL`、`UNKNOWN` | 不调用 LLM，不执行文件或 Shell 操作，也不能完整解释任意 Shell 语义 |
| **Hook** | 将策略决策接入已配置的宿主工具路径，执行审计或拒绝 | 可选且需人工接入；实际效果受宿主版本、工具覆盖和信任配置限制 |

### Skill：开发行为约束

Skill 重点帮助 Agent：

- 对齐用户目标，区分已授权工作、建议和普通讨论；
- 保护未提交修改和并行工作，避免无关重构与范围扩张；
- 在常规读取、编码与调试中保持自主，不为每一步反复请求批准；
- 对删除数据、生产变更、强制推送、外部副作用等高风险操作请求具体授权；
- 在完成用户目标后停止，而不是继续增加可选功能。

核心规则位于 [SKILL.md](SKILL.md)。高风险情形可按需查阅[风险与授权边界](references/risk-boundaries.md)；涉及人工验收或后续反馈时可查阅[人工验收与反馈](references/human-acceptance.md)。Skill 不会覆盖宿主指令或系统保护。

### Adaptive Guardrails：默认统一策略

新运行时默认使用单一 **ADAPTIVE** 策略，普通用户无需选择运行模式。

- 对可信结构化上下文中已识别的敏感文件、受保护路径和工作区外目标返回拒绝；
- 对已识别的破坏性、外部副作用或生产相关操作返回 `REQUIRE_APPROVAL`；宿主无法可靠对接审批时，Hook 拒绝该操作，不会自行放行；
- 对明确安全的常规开发操作返回 `ALLOW`，不额外增加阻断；
- 对无法可靠分类的操作返回 `UNKNOWN`。Adaptive Hook 仅审计并 abstain：不把未知操作当作安全，也不主动授予额外权限；后续边界仍由宿主 Sandbox 和权限机制处理。

已有 **OBSERVE / PROTECT / STRICT** bundle 保持原有行为，只有显式迁移才会创建新的 Adaptive bundle，不会静默降低既有保护配置。

## 安装 Skill

需要 Git 和 Python 3.11+。获取源码后，在源码仓库目录执行；将示例路径替换为**已存在的项目目录绝对路径**：

```sh
git clone --depth 1 https://github.com/yuan-ww/universal-development-guardrails.git
cd universal-development-guardrails
python3.11 -I guardrails/runner.py install-skill --workspace "/absolute/path/to/your-project"
```

默认安装位置为目标项目的 `.agents/skills/universal-development-guardrails/`。安装过程不会覆盖现有目录、不会修改全局配置、不会授予信任，也不会启用 Hook。

在目标项目中显式调用 `$universal-development-guardrails`。Claude Code 和 Cursor 可分别附加 `--agent claude`、`--agent cursor`，安装到项目的 `.claude/skills/`、`.cursor/skills/`。卸载等后续命令应使用相同的 `--agent` 参数。Windows 可用 `py -3.11` 或其他已安装的 Python 3.11+ 替换 `python3.11`。

安装位置、恢复方式和卸载细节见[快速指南](docs/quickstart.md)。

## 可选：策略运行时与 Hook

仅使用 Skill 不需要本节。需要为项目生成策略运行时时，在源码仓库目录执行：

```sh
python3.11 -I guardrails/runner.py install --workspace "/absolute/path/to/your-project"
```

该命令生成默认 **ADAPTIVE** bundle，其中包含运行时代码、`policy.json`、Hook 配置片段和文件清单。bundle 位于项目内，不等于已启用 Hook，也不是安全隔离；应保护解释器、策略、运行时代码及其父目录。

### 启用 Hook

启用前应审阅生成的配置片段，并保留现有 Sandbox、审批和其他 Hook。

**Codex：** 备份项目的 `.codex/hooks.json`，将 bundle 内 `codex-hooks.json` 的 `hooks.PreToolUse` 条目**人工合并**到项目配置中，保留其他 Hook。随后在宿主中启用并信任该项目配置。

**Claude Code：** 使用 bundle 提供的适配器和宿主配置步骤。**Cursor：** 当前没有 UDG Hook 适配器。

不要叠加多个 UDG Hook bundle；生成 Hook 配置也不会扩大 Shell 白名单或自行声明授权。

### 遗留模式迁移与回退

已存在的 OBSERVE、PROTECT、STRICT bundle 不会被自动改写。使用下列命令从遗留 bundle 创建独立的 Adaptive bundle：

```sh
python3.11 -I guardrails/runner.py migrate \
  --source "/absolute/path/to/legacy-bundle" \
  --destination "/absolute/path/to/udg-adaptive-bundle"
```

随后人工将宿主 Hook 从旧 bundle 切换为新 bundle。回退时，先将宿主 Hook 改回旧 bundle，再执行：

```sh
python3.11 -I guardrails/runner.py rollback-migration \
  --destination "/absolute/path/to/udg-adaptive-bundle"
```

回退只移除该新 bundle，不会修改旧 bundle 或其他宿主配置。仍可通过 `--mode OBSERVE|PROTECT|STRICT` 创建新的遗留兼容 bundle。

### 单独使用策略引擎

`evaluate` 仅计算拟议操作的策略决策，不会执行该操作：

```sh
printf '%s' '{"kind":"write","paths":["src/app.txt"]}' \
  | python3.11 -m guardrails evaluate --policy "/absolute/path/to/policy.json"
python3.11 -m guardrails --help
```

可从已安装 bundle 的 `policy.json` 开始配置，格式见[策略格式](docs/policy-format.md)。结构化上下文必须来自可信调用方；模型自报的参数不是授权。决策退出码为 `ALLOW=0`、`DENY=2`、`REQUIRE_APPROVAL=3`；`UNKNOWN` 不会被 CLI 伪装为已批准的操作。

## 停用、卸载与升级

先从宿主配置中移除 UDG Hook 条目及可选原生规则，保留其他配置。随后按需执行：

```sh
python3.11 -I guardrails/runner.py uninstall \
  --destination "/absolute/path/to/your-project/.guardrails/udg-bundle"
python3.11 -I guardrails/runner.py uninstall-skill \
  --workspace "/absolute/path/to/your-project"
```

卸载遇到用户修改、额外文件或 symlink 时会拒绝删除，以避免误删用户内容。升级时先保存自定义内容，再选择保守卸载重装或安装到新目录；UDG 不会静默覆盖现有配置。

## 边界与限制

- **Skill 不是强制安全边界。** 它是对 Agent 的开发行为建议，不具备权限授予或工具拦截能力。
- **Hook 依赖宿主。** 未经过 Hook 的工具、子进程副作用及其他旁路不受 UDG 控制。宿主在 Hook 崩溃、超时或配置失效时可能采取 fail-open 行为。
- **UDG 不能替代 Sandbox。** 路径检查仍存在竞态、硬链接和平台差异；同权限进程可修改自身策略或 Hook。文件、网络和执行边界仍应由宿主 Sandbox 与操作系统权限负责。
- **可信上下文是前提。** UDG 不猜测缺失的执行目录或授权，也不把未知操作主动升级为许可。
- **多宿主支持范围不同。** Codex、Claude Code、Cursor 的配置接口和行为并不相同；应按各宿主能力部署，不将一个宿主的配置结果视为其他宿主的保障。

更多设计信息见[架构](docs/architecture.md)、[安全模型](docs/security-model.md)、[Adaptive 策略](docs/adaptive-strategy.md)和[平台说明](docs/platforms.md)。

## 许可证

本项目采用 [MIT License](LICENSE)，版权所有 © 2026 yuan-ww。
允许按照许可证条款使用、修改、分发及商业使用；复制或分发软件的全部或重要部分时须保留版权及许可声明。软件按“原样”提供，不提供担保。
