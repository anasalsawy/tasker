# TASKER ACTION LOOP BUG FIX

## Problem
The computer-use agent (Tasker) has a broken action execution loop:
- Sometimes repeats the first action continuously
- Sometimes stalls waiting for state change
- Sometimes skips actions or executes them out of order
- No proper validation that actions actually succeeded

## Root Cause
In `backend/routers/aiagent/generic.py`, the `/next_step` endpoint:
1. Sends actions to desktop
2. **DOES NOT WAIT** for desktop to confirm execution
3. **DOES NOT VERIFY** the state changed as expected
4. Immediately asks LLM for next action with old/stale state
5. LLM repeats previous action because state didn't change

## Solution Required

The action execution needs:

1. **Action Execution Confirmation Loop**
   ```
   Send action to desktop
   ↓
   WAIT for execution confirmation
   ↓
   Get new screenshot/state
   ↓
   Verify state changed (element is gone, app opened, etc.)
   ↓
   If state matches expected: proceed to next action
   ↓
   If state doesn't match: retry action or fail
   ```

2. **State Validation**
   - Before sending next action, screenshot should show:
     - Previous action's effects are visible
     - System is in expected state
     - No error dialogs or unexpected states
   - If not: LLM should analyze discrepancy and retry

3. **Action Queue Management**
   - Only one action executes at a time
   - Must complete/confirm before next starts
   - No parallel execution that can interfere

4. **Timeout Protection**
   - Each action has max 30s to execute
   - If no state change in 30s: fail action, proceed
   - Prevents infinite stalls

## Files to Fix
- `backend/routers/aiagent/generic.py` - `/next_step` endpoint
  - Add action execution confirmation logic
  - Add state validation after each action
  - Add retry logic for failed actions

- `backend/schemas/aiagent.py` - NextStepRequest/Response
  - Add `action_execution_status` field
  - Add `action_completed_at` timestamp
  - Add `state_change_detected` boolean

- `backend/utils/agentic_tools.py` - run_tool_server_side()
  - Add confirmation callback mechanism
  - Add state comparison logic
  - Add retry counting

## Implementation Priority
1. CRITICAL: Fix action confirmation loop (no more repeating actions)
2. CRITICAL: Add state validation (verify action succeeded)
3. IMPORTANT: Add timeout protection
4. NICE: Add retry logic for transient failures

## Testing
After fix, test:
- Single action completes without repeating
- Multi-step task doesn't stall
- State changes are visible between actions
- Failed actions get proper error handling

This is why Tasker sometimes works (lucky timing) and sometimes fails (race conditions).
