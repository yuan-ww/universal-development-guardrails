# Adaptive Guardrails implementation and evidence boundary

**Status: implemented as the v2 default for new bundles, with constrained
Codex real-host canaries. It is not a complete Shell security boundary or a
replacement for host Sandbox/approval.** Existing v1 `OBSERVE`, `PROTECT`, and
`STRICT` policies, bundles and Hook snippets remain behaviorally unchanged
until an explicit migration creates a separate v2 bundle.

## Problem and non-goal

`PROTECT` conservatively maps an unknown operation to host approval or denial.
That is appropriate for a reliably unknown, high-impact operation, but in the
tested Codex Bash path a missing per-tool execution directory turns ordinary
relative read, test, and Git commands into the same unknown class. The measured
development sample consequently saw 11 of 12 explicitly authorized commands
refused in `PROTECT`.

Adaptive Guardrails must not solve that result by guessing the execution
directory, adding a broad command allowlist, accepting an Agent-supplied
approval field, or claiming an unsupported approval bridge. It also cannot make
an outer Hook launch failure fail closed. Its purpose is to give one default
policy for new installations only after evidence shows that it improves normal
development without silently weakening protection that is known to work.

## Decision model

The implementation candidate needs a fourth *classification*, separate from the
current three host-facing decisions:

| Classification | Preconditions | Adaptive Hook action | Claim allowed |
|---|---|---|---|
| Known routine | Trusted schema and sufficient scoped context establish an ordinary operation inside the workspace | Abstain; preserve native host approval and Sandbox | No extra UDG block was added |
| Known violation | Trusted schema establishes sensitive access, protected-path modification, or an outside-workspace target | Deny | The tested Hook path refused this known violation |
| Known high risk | Trusted schema establishes destructive Git, data destruction, external, production, or opaque execution | Request real native approval only where that bridge is verified; otherwise deny | Approval was requested or the action was denied on the named host/mode |
| Unknown | Schema, execution target, or risk semantics cannot be established reliably | Record `UNKNOWN` and abstain; retain native host approval and Sandbox | Coverage is unknown, not safe or protected |
| Invalid or internal failure | Malformed policy/event, worker failure, or audit failure after a non-observe decision | Deny if the Hook is reached | Only the worker/Hook response is fail-closed; outer Hook failures remain a host limitation |

`UNKNOWN` must be a separate Adaptive decision record. Reusing `ALLOW` would
incorrectly imply that UDG understood the operation; reusing
`REQUIRE_APPROVAL` would repeat the normal-development block rate on hosts
without a verified approval bridge. An **abstain** response is not a host
permission grant: it must be the empty response used for a routine `ALLOW`,
leaving the host's own policy in force.

This is a coverage decision, not a generalized Shell parser. Recognizers may
grow only for a host schema and command grammar with specific positive, negative,
and real-host evidence. An unknown `rm` must not become routine merely because
normal commands are being made less disruptive.

## Compatibility and migration

1. A future policy format uses a versioned `ADAPTIVE` strategy rather than
   reinterpreting an existing `mode` value.
2. Existing bundles remain behaviorally unchanged. In particular, `STRICT`
   cannot silently become abstain-on-unknown behavior.
3. Migration creates a separately named, validated bundle and presents a
   reversible, manual Hook-configuration change. It never overwrites a bundle
   or merges host configuration automatically.
4. The migration report must show old mode, new strategy, Hook locations,
   platform/version evidence, and rollback steps. If any are absent, retain the
   old installation.
5. Rollback restores the previous Hook entry and bundle. Legacy mode code stays
   until migration and host tests justify a separate removal decision.

## Evidence exercised for this implementation

All results identify UDG revision, policy revision, host and OS version, Hook
configuration, native approval/Sandbox state, and data scope. Failures,
unavailable checks, and no-Hook controls are reported separately.

| Gate | Current assertion or evidence |
|---|---|
| Policy invariants | Every known sensitive, protected, outside-workspace, and destructive category keeps its present deny/approval semantics; no policy field lets an Agent assert approval. |
| Unknown semantics | Missing or untrusted execution context records `UNKNOWN`, does not become routine `ALLOW`, and does not grant host permission. |
| Normal development | On macOS Codex CLI 0.164.0-alpha.11.1, compare no Hook, legacy `PROTECT`, and first-install Adaptive on the documented 12-command sample. Report eligible commands, UDG refusals, host failures, and filesystem effects. |
| High-risk coverage | Unit/Hook tests cover categories. Real Codex canaries cover protected paths, sensitive reads/writes, workspace escape, destructive Git, external classification, unknown tools and exact known-scope allows. Production/data-destruction host variants remain unverified. |
| Failure behavior | Test malformed input, worker crash, internal timeout, audit failure, outer Hook crash/timeout/bad output, and Hook-disabled controls. Do not label an observed outer fail-open path as protected. |
| Host compatibility | Run isolated canaries per supported host/version, including actual approval behavior. A schema test or generated configuration is not enforcement evidence. |
| Cost | Verify deterministic local evaluation, no per-operation model call, and report added latency, tool calls, and any measurable Token change. |
| Migration | Exercise validation, new-bundle creation, manual enablement, rollback, modified-bundle preservation, and legacy non-migration. |

A lower normal-command refusal rate is insufficient if a known dangerous case
loses documented protection; a higher interception count is insufficient if
ordinary development becomes unusable. Skill-quality experiments remain
separate from Hook experiments, as described in [verification](verification.md).

## Current implementation status

- Policy v2 is exclusively `ADAPTIVE`; rule files cannot declare `UNKNOWN`.
  The engine records it only when trusted normalization cannot classify an
  operation. The Hook maps it to an empty abstain response rather than ALLOW
  or a permission grant.
- New installs create v2 Adaptive bundles. `migrate`, `verify-migration`, and
  `rollback-migration` create, check, and conservatively remove a separate
  bundle; they never edit a legacy bundle or host configuration.
- Current Codex normalization intentionally lacks a trustworthy actual Bash
  execution directory. Existing host evidence supports only explicit absolute
  operands and an absolute `git -C` subset. It does not justify treating
  relative development commands as known routine operations.
- On macOS, `0.164.0-alpha.11.1` with Python 3.12.14 and a local scripted
  provider completed isolated Adaptive coverage and development canaries. All
  12 authorized development commands executed without a UDG refusal; 11 were
  still recorded UNKNOWN because the actual workdir was absent. The same run
  refused known protected, sensitive, outside-workspace, external and
  destructive-Git examples before execution. This is evidence for those named
  Codex paths only, not all tools, host versions or real model behavior.
- No current result proves a Codex approval bridge, repairs outer fail-open
  behavior, or establishes lower Token cost. These remain unsupported or
  unverified.

## Remaining stop condition

Do not widen Shell recognition, grant extra host permission, or remove legacy
modes based on these canaries. If the host still omits execution context,
retain UNKNOWN/abstain rather than treating relative development operations as
safe. Before claiming broader protection, run retained canaries for each host
and tool path, including native approval and failure behavior.
