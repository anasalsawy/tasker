# Tasker dual-lobe execution

Tasker keeps NeuralAgent's existing execution path and adds an opt-in look-ahead lane.

## Runtime model

1. The inherited /next_step endpoint supplies the first accepted batch.
2. Lobe A executes that batch on the desktop.
3. While A is executing, lobe B calls /dual_lobe/predict.
4. The prediction is stateless. It cannot advance the plan, write an action message, or mark a subtask complete.
5. The screen observer samples the desktop continuously during execution.
6. After A finishes, Tasker checks the observed boundary. A predicted batch is accepted only when the handoff policy permits it.
7. Tasker executes B and calls /dual_lobe/commit only after execution. The backend then records B and applies completion/tool state changes.
8. A failed look-ahead, timeout, or boundary mismatch is discarded. Tasker asks the inherited /next_step path for a fresh batch.

The important invariant is:

predicted state -> observed screen -> accepted handoff

A model's statement that an action succeeded is not treated as screen evidence.

## Manually selected lobe-B profiles

The profile is selected by the operator; Tasker does not switch it automatically.

- screen-aware (default): continuous observer plus predicted-boundary handoff checks.
- predictive: permits look-ahead when a post-execution observation exists; useful for measuring latency, but it is less strict.
- gatekeeper: reserved for the strict policy; it requires the same observation path and is intended for additional policy checks.
- off: the original NeuralAgent single-loop path, useful as the control condition.

On Windows PowerShell:

    $env:TASKER_DUAL_LOBE_PROFILE = "screen-aware"

Control condition:

    $env:TASKER_DUAL_LOBE_PROFILE = "off"

Other settings:

    $env:TASKER_SCREEN_HZ = "4"
    $env:TASKER_PREVIEW_TIMEOUT = "120"
    $env:TASKER_DUAL_LOBE_MAX_BATCHES = "20"

## What this does and does not claim

This is a real concurrency and state-handoff implementation, not a model-quality benchmark. The speed benefit depends on the provider returning B before A finishes. A slow provider still produces a safe fallback, not a fabricated speedup.

The observer currently records screenshot hashes, foreground-app hints, and UI counts. It does not prove semantic success for every application. For destructive or high-impact actions, a stronger application-specific verifier should be added before enabling unattended execution.

## Control comparison

For a fair experiment, run the same task twice:

- control: TASKER_DUAL_LOBE_PROFILE=off
- treatment: TASKER_DUAL_LOBE_PROFILE=screen-aware

Record provider, model, prompt, screenshot availability, total elapsed time, batches, actions, look-ahead readiness, rejects, fallbacks, and final task state. Unit tests of the coordinator do not count as real provider-backed execution.
