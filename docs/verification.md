# 验证方式与效果边界

本发布快照保留产品源码、必要测试及复现入口，不包含内部真实模型实验框架、候选 Skill、原始轨迹或研发报告。

## 离线核心与安装校验

```sh
python3.11 -m unittest discover -s tests -v
ruff check guardrails tests
python3.11 -m compileall -q guardrails tests
python3.11 -m guardrails evaluate-scenarios --trace tests/fixtures/scenarios.json
python3.11 tests/integration/package_install.py
```

运行时仅需 Python 3.11+ 标准库。wheel 往返测试会使用隔离 venv 和可用的构建工具；缺少非必要本地构建依赖时，不代表运行时安装失败。CI 自行安装其检查所需工具。

保留的回归覆盖策略决策、冲突与优先级、保护路径与敏感类别、异常输入、窄 Shell 语法、Hook 契约与故障、脱敏审计、真实多进程审计、用户修改保护、安装异常与保守卸载。并发审计仍有已知 SQLite 锁冲突风险；一次通过不代表任意并发负载都可靠。不要通过弱化断言或反复重试掩盖失败。

12 场景评分入口只对输入事实评分；随包 fixture、正反例和缺失证据测试是评分器回归，不能证明 Agent 的真实行为或 Skill 的效果。

## Codex 宿主复现

```sh
python3.11 tests/integration/codex_host.py --codex /absolute/path/to/codex --suite coverage
python3.11 tests/integration/codex_host.py --codex /absolute/path/to/codex --suite development
```

该测试使用真实 Codex CLI 0.160.0、真实工具和 Hook，但模型响应由本地脚本服务提供，不调用真实付费模型，不能当作 Agent 效果实验。仅在临时合成项目运行，不修改用户全局配置。

覆盖包含无 Hook 控制、真实拒绝后的文件副作用、apply_patch 保护路径、合成敏感文件、第二个测试根目录、未知工具及明确绝对路径；另有未信任、外层崩溃、超时、坏输出的 fail-open 反例。反例通过表示观察到了放行，绝非这些故障被安全阻止。不能外推全部工具或其他宿主版本。

开发命令限定样本见[误拦截与模式限制](development-measurements.md)：显式 PROTECT 曾误拦截 12 条常规命令中的 11 条；默认 OBSERVE 不额外执行策略阻断，不代表安全判断已改善。Hook 的会话 cwd 不是可信的逐工具实际目录，见[执行上下文限制](execution-context.md)。

## Claude Code 人工集成

真实宿主集成仍为 **Unverified**；文件安装与输出契约测试不等于实际拦截或审批桥接。需要人工验证时，只在隔离合成项目中：

1. 记录 Claude 版本、权限和沙箱状态，按 README 显式选择模式并人工合并 Hook，保留已有配置。
2. 检查普通读写、合成敏感文件拒绝及实际文件副作用；在 default 交互权限模式验证 ask 提示和拒绝后的无执行。
3. 验证原生 deny 仍优先，错误/超时与 onFailure=block 的实际效果；测试结束恢复配置。
4. 不使用真实凭据、生产数据或 bypassPermissions 来制造通过。失败保留为失败，未验证能力不标 Enforced。

Cursor 没有本项目 Hook 适配器；安装目录存在不等于真实 Skill 发现或遵守。

## Skill 的行为效果

正式文本重点是目标授权、跨会话连续性及适度工程工作。现有真实 A/B 尚未观察到明确的防跑偏增量收益；不能把文本覆盖、成功加载、一次任务通过或限定样本 Token 变化解释为普遍有效。研发实验与原始证据不随公开快照发布。

Skill 是 Advisory，OBSERVE 是 Audit-only，实际执行边界依赖宿主 Sandbox 和 OS 权限。完整能力分类见[平台矩阵](platforms.md)和[安全模型](security-model.md)。

## CI

保留 Linux Python 3.11/3.12/3.13、macOS/Windows Python 3.12 核心与安装测试，以及固定 Codex CLI 0.160.0 的宿主套件。CI 使用 contents:read，不需要模型 API Key、数据库服务或 Docker。只有实际成功的运行才算云端通过；配置存在不能代替结果。
