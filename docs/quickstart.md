# 快速安装、验证与卸载

这是 Engineering Preview，不是正式 Release，也未提供 PyPI / pipx / npx 分发承诺。安装器不自动配置或信任 Hook，不修改用户全局设置，不创建后台服务。默认 OBSERVE 只有观察能力。

## 1. 获取源码

需要 Git 与 Python 3.11+。在用于存放工具源码的目录执行（不必在被开发项目中克隆）：

```sh
git clone --depth 1 https://github.com/yuan-ww/universal-development-guardrails.git
```

审阅来源和实际提交。以上获取 main，已包含快捷安装入口。不提供 curl 管道执行远程代码的方案。以下路径假设源码目录名为 universal-development-guardrails；按实际位置调整。

将 `/absolute/path/to/your-project` 换成一个**已存在的项目目录**。安装不是授权模型修改其他项目。Windows PowerShell 可使用 `py -3.11 -I` 替代 `python3.11 -I`，或选择已安装的其他 3.11+ Python。

## 2A. 只安装 Skill（建议先从这里开始）

```sh
python3.11 -I universal-development-guardrails/guardrails/runner.py install-skill --workspace "/absolute/path/to/your-project"
python3.11 -I universal-development-guardrails/guardrails/runner.py verify-skill --workspace "/absolute/path/to/your-project"
```

默认目标为 `.agents/skills/universal-development-guardrails/`，包含未改写的 SKILL.md、references/risk-boundaries.md、LICENSE 和 manifest.json。与现有目录冲突会失败，不覆盖、不自动更新。校验只证明安装文件与清单一致，不是签名、受信证明或宿主加载证明。

在目标项目启动 Codex，检查 `/skills`，显式调用 `$universal-development-guardrails`。按[官方发现规则](https://learn.chatgpt.com/docs/build-skills)，项目目录和启动位置影响发现；本轮真实发现验证是在隔离 Git 项目中检查模型收到的 Skill 名称/描述，并有未安装对照。不声称验证了模型遵守效果。首次未显示时重启、检查启动项目与是否被禁用；安装器不会自动修改全局开关。

`--agent claude` 改放到 `.claude/skills/`，`--agent cursor` 改放到 `.cursor/skills/`；verify / uninstall 必须使用相同 agent。它们的文件放置有测试，真实宿主发现/加载仍 Unverified。文本 Skill 是 Advisory，不安装策略引擎、不启用权限、不拦截工具。

卸载自动安装的 Skill：

```sh
python3.11 -I universal-development-guardrails/guardrails/runner.py uninstall-skill --workspace "/absolute/path/to/your-project"
```

仅移除完全匹配的副本；有用户修改、额外文件/空目录、symlink 或未完成标记时拒绝。父级 skills 目录及其他 Skill 不删除。手工安装且没有清单的目录不交给此命令删除；先备份并自行处理。

## 2B. 可选：生成观察运行时

```sh
python3.11 -I universal-development-guardrails/guardrails/runner.py install --workspace "/absolute/path/to/your-project"
python3.11 -I universal-development-guardrails/guardrails/runner.py verify-install --destination "/absolute/path/to/your-project/.guardrails/udg-bundle"
```

默认 `mode=OBSERVE`，目标 `.guardrails/udg-bundle`；成功 JSON 列出实际 destination、mode、hook_configs，并标明手动启用要求。省略目标的快捷方式拒绝 `.guardrails` symlink，避免默默转向其他目录。自定义位置仍使用显式 `--destination`，PROTECT / STRICT 仍需显式 `--mode`，不会自动降低已有模式。

生成 bundle **不等于启用 Hook**。按 [README 的平台步骤](../README.md#启用-hook)备份现有配置、人工合并所选 Hook、检查信任和重新启动。不替换宿主原有 Sandbox / 审批设置；不要通过 trust bypass、allow 白名单或敏感实物试验来加速部署。安装器不声称已验证你的实际宿主环境。

默认项目内 bundle 为快速评估用途；同一 Agent 可写的代码和策略不是对抗性边界。需要更高可信时放在受操作者控制的显式目标，保护父目录和解释器。Hook 固定绑定安装时的 Python：删除或移动该解释器/虚拟环境会使 Hook 失效，Codex 外层可能 fail-open。生成后可独立执行 bundle 的 runner，不依赖源码 checkout；但必须保留所绑定 Python。

卸载运行时：先从项目配置中移除本次 UDG Hook（保留其他条目），重新启动确认停用，然后执行：

```sh
python3.11 -I universal-development-guardrails/guardrails/runner.py uninstall --destination "/absolute/path/to/your-project/.guardrails/udg-bundle"
```

修改过的文件不会被静默删除，审计目录不会删除；`.guardrails` 父目录也保留。OBSERVE 不额外保护敏感/越界/危险操作；PROTECT 的上下文缺口与误拦截、外层 fail-open 仍存在，见[安全模型](security-model.md)。

## 3. 可选：安装 Python 包后使用 udg

源码入口已经足够，不需要本步骤。在仓库根目录创建独立工具虚拟环境，例如 POSIX：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/udg install-skill --workspace "/absolute/path/to/your-project"
.venv/bin/udg install --workspace "/absolute/path/to/your-project"
```

Windows 使用 `.venv\Scripts\python.exe` 和 `.venv\Scripts\udg.exe`。真实 wheel 安装测试在全新 venv、源码外的 cwd 执行安装/验证/卸载，确认数据文件随包安装，且有相同的 Skill / 许可内容。没有仅凭本机源码存在就宣称 wheel 可用。不要把开发依赖 Ruff 当成最终使用者依赖。

## 故障、升级与恢复

- Python 版本不满足：选择已安装的 3.11+；安装器不会下载 Python 或改系统 PATH。
- 目录已经存在：不要加覆盖参数或先删除用户目录。先保存修改，校验已有安装；要更换版本/模式，选择新 bundle 目录并按 README 显式切换 Hook。
- 文件校验失败 / `.udg-installing`：不要启用残留目录。先保存用户文件，再人工处理或选新目录；没有不检查内容的自动清理。
- Skill 更新：先确认副本未经修改并用 uninstall-skill 保守卸载，再安装审阅过的新版本。自定义副本先备份或选择独立项目，不静默覆盖。
- 运行时失效：停用相应 Hook、保留证据，检查 Python 路径、配置来源及信任。不要把无审计或安装成功当作保护已生效。

安装器仅复制本地已获取的文件，不联网执行安装脚本。配置自动合并、全局安装、插件商店分发和真实模型行为评估均不是本快捷入口提供的能力。
