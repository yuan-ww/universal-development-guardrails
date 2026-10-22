# Architecture

一个 Python 包、一个 JSON 策略、两个 PreToolUse 输出适配器。无 daemon、LLM 服务或网络依赖。

1. 宿主事件进入绝对路径 runner.py，Python `-I` 排除 cwd/PYTHONPATH 导入污染。
2. hooks.py 启动 worker，默认内部期限 2 秒，短于生成的宿主期限 5 秒。只解析和判定，不执行提议操作。
3. normalize.py 按宿主 schema 归一化，授权配置只来自显式 policy 文件，不相信工具参数自称批准。未知工具不猜语义。
4. policy.py 校验、规范化路径、计算并解决候选规则冲突。核心不知道任何 Agent 平台。
5. 输出映射：ALLOW 为空对象继续宿主原权限流程，DENY 拒绝；Claude default 下审批映射 ask，其他情况拒绝。
6. storage.py 将允许列表字段写入 SQLite，PROTECT/STRICT 审计失败拒绝，OBSERVE 提示。连接关闭，无常驻组件。

安装器只创建 bundle 和片段，操作者显式合并并完成宿主信任。就绪协议为：带标记私有构建 → 独占目标/文件 → 清单最后写入 → 内容/策略校验 → 移除未完成标记。异常按文件内容校验回滚，不递归删除目标；保留修改时保留未完成状态。不是原子目录替换。校验清单不是签名，不能抵御能同时修改清单和代码的攻击者。卸载先预检全部目标，再逐个移除已验证文件；用户修改会保留并报错。

Codex Bash 的会话 cwd 不充当实际执行 cwd：0.160.0 丢失工具 workdir，依赖该上下文的相对操作进入 unknown。显式绝对参数只解决受支持窄语法的目标，不扩展进程权限或沙箱范围。

SQLite 事务处理并发审计。revision/check_revision 提供合作式修订比较，能检测比较前重叠编辑，不锁定后续写入。真实多 Agent 优先用 worktree 或文件工具内部原子 CAS。

扩展适配器先补官方契约、输入映射、审批/故障测试，再做真实宿主 canary；契约测试不自动获得 Enforced。未知 MCP schema 不按名字猜权限。扩大 Shell 语法应引入经验证的解析/执行边界，不堆叠关键词黑名单。
