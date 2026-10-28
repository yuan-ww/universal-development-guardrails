# Human acceptance and feedback

Use this reference only when human acceptance is appropriate or a person has
provided acceptance feedback. It complements automated checks; it does not turn
every code change into a manual test process.

## When to request acceptance

Human review is most useful for requirement fit, a real business flow, visual or
interaction quality, real data or permission behavior, or an environment that
the agent cannot safely access. A small, low-risk, non-user-visible change may
need only the relevant automated checks and an accurate delivery report.

## Compact handoff

Give the reviewer only the information needed to judge the change:

- what was implemented, and the version or revision to review;
- the actual entry point, environment, prerequisites, and any supplied test
  data;
- the shortest action path and the expected result;
- the automated checks actually run and their results;
- meaningful environment or data limitations, unverified behavior, and known
  issues.

State a result as **Human Accepted** only after an explicit human confirmation.
Do not substitute a local test, mock, CI job, deployment, or absence of feedback
for that confirmation.

## Handoff template

Use this only when a human review is warranted; omit fields that are genuinely
not applicable rather than inventing a test stage.

```text
Implemented: <behavior changed>
Revision / environment: <reviewable version and actual environment>
Entry point: <URL, command, screen, or other access path>
Prerequisites / test data: <only what the reviewer needs>
Steps and expected result: <short path and observable outcome>
Automated checks completed: <command or CI result actually run>
Not verified / limits: <environment, data, permission, or coverage limits>
Known issues: <none, or a concise factual list>
```

Do not include credentials, production data, or an implication that a reviewer
must repeat checks the agent already completed. A reviewer can accept, reject,
or clarify the behavior; silence is not acceptance.

## Handling feedback

1. Record the observed behavior and attempt a focused reproduction when that is
   safe and practical.
2. Classify it before changing code: an implementation defect, a requirement
   clarification, or a new request. Do not silently convert one into another.
3. Repair only the confirmed defect within the existing authorization. Request
   direction before a clarification or new request would materially broaden
   scope.
4. Verify the affected behavior and the smallest relevant regression surface.
   Do not weaken tests or make unrelated refactors to make the feedback disappear.
5. Submit the result for renewed review when the outcome still requires human
   judgment. Otherwise report exactly what was verified and what remains
   unverified.

If reproduction or repair yields no new evidence, stop retrying and report the
blocker with the evidence already collected.
