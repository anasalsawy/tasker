"""Tasker's bounded dual-lobe execution coordinator.

This module is deliberately independent from the model provider.  NeuralAgent's
existing desktop agent remains the actuator; this coordinator only manages
look-ahead, observation, and handoff.

Lobe A executes a batch that has already been accepted.  Lobe B prepares the
next batch against A's predicted boundary.  B's result is not considered true
until the observer records the post-A screen state and the handoff checks pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional


PROFILE_PREDICTIVE = "predictive"
PROFILE_SCREEN_AWARE = "screen-aware"
PROFILE_GATEKEEPER = "gatekeeper"
PROFILE_OFF = "off"
VALID_PROFILES = {
    PROFILE_PREDICTIVE,
    PROFILE_SCREEN_AWARE,
    PROFILE_GATEKEEPER,
    PROFILE_OFF,
}


def _now() -> float:
    return time.time()


@dataclass(frozen=True)
class ScreenObservation:
    captured_at: float
    screen_hash: str
    foreground_app: Optional[str] = None
    interactive_count: int = 0
    running_app_count: int = 0

    @classmethod
    def from_payload(cls, payload: Optional[Mapping[str, Any]]) -> "ScreenObservation":
        payload = payload or {}
        image = str(payload.get("screenshot_b64") or "")
        screen_hash = str(payload.get("screen_hash") or "")
        if not screen_hash:
            screen_hash = hashlib.sha256(image.encode("utf-8")).hexdigest() if image else ""
        return cls(
            captured_at=float(payload.get("captured_at") or _now()),
            screen_hash=screen_hash,
            foreground_app=payload.get("foreground_app"),
            interactive_count=int(payload.get("interactive_count") or 0),
            running_app_count=int(payload.get("running_app_count") or 0),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "screen_hash": self.screen_hash,
            "foreground_app": self.foreground_app,
            "interactive_count": self.interactive_count,
            "running_app_count": self.running_app_count,
        }


@dataclass(frozen=True)
class PredictedBoundary:
    batch_id: str
    action_count: int
    foreground_app: Optional[str]
    url: Optional[str]
    expected_transition: str
    coordinate_space: str = "screen-1280x720"
    requires_visual_change: bool = True
    confidence: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "action_count": self.action_count,
            "foreground_app": self.foreground_app,
            "url": self.url,
            "expected_transition": self.expected_transition,
            "coordinate_space": self.coordinate_space,
            "requires_visual_change": self.requires_visual_change,
            "confidence": self.confidence,
        }


@dataclass
class LobeBatch:
    batch_id: str
    source_lobe: str
    response: Dict[str, Any]
    predicted_boundary: PredictedBoundary
    needs_commit: bool = False

    @property
    def actions(self) -> List[Dict[str, Any]]:
        actions = self.response.get("actions", [])
        return actions if isinstance(actions, list) else []

    @property
    def action_count(self) -> int:
        return len(self.actions)


@dataclass
class DualLobeReport:
    status: str
    batches_executed: int
    actions_executed: int
    lookahead_ready: int
    lookahead_rejected: int
    screen_updates: int
    trace: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "batches_executed": self.batches_executed,
            "actions_executed": self.actions_executed,
            "lookahead_ready": self.lookahead_ready,
            "lookahead_rejected": self.lookahead_rejected,
            "screen_updates": self.screen_updates,
            "trace": list(self.trace),
        }


def batch_id_for(response: Mapping[str, Any], ordinal: int, source_lobe: str) -> str:
    explicit = response.get("batch_id")
    if explicit:
        return str(explicit)
    actions = response.get("actions", [])
    digest = hashlib.sha1(
        json.dumps(actions, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:10]
    return "{}-{}-{}".format(source_lobe.lower(), ordinal, digest)


def predict_boundary(
    response: Mapping[str, Any],
    batch_id: str,
    observation: Optional[ScreenObservation] = None,
) -> PredictedBoundary:
    actions = response.get("actions", [])
    actions = actions if isinstance(actions, list) else []
    foreground = observation.foreground_app if observation else None
    url = None
    transitions: List[str] = []

    for action in actions:
        if not isinstance(action, Mapping):
            continue
        kind = action.get("action")
        params = action.get("params") or {}
        if kind in {"launch_app", "focus_app"}:
            foreground = params.get("app_name") or foreground
            transitions.append("{} {}".format(kind, params.get("app_name", "")))
        elif kind == "launch_browser":
            url = params.get("url")
            transitions.append("open {}".format(url or "browser"))
        elif kind in {"left_click", "double_click", "right_click", "click"}:
            transitions.append("click visible target")
        elif kind in {"type", "key", "key_combo"}:
            transitions.append("input changes focused control")
        elif kind == "scroll":
            transitions.append("scroll visible surface")
        elif kind == "wait":
            transitions.append("wait for UI")
        elif kind in {"subtask_completed", "task_completed"}:
            transitions.append("completion boundary")

    current_state = response.get("current_state") or {}
    next_goal = current_state.get("next_goal") or current_state.get("next_steps") or ""
    if next_goal:
        transitions.append(str(next_goal))

    return PredictedBoundary(
        batch_id=batch_id,
        action_count=len(actions),
        foreground_app=foreground,
        url=url,
        expected_transition="; ".join(transitions) or "screen state remains observable",
        requires_visual_change=not all(
            isinstance(action, Mapping) and action.get("action") == "wait"
            for action in actions
        ),
        confidence=float(response.get("confidence") or 0.0),
    )


class ScreenObserver:
    """Continuously samples the screen and publishes the newest observation."""

    def __init__(
        self,
        capture: Callable[[], Mapping[str, Any]],
        interval: Optional[float] = None,
        trace: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.capture = capture
        configured_hz = float(os.getenv("TASKER_SCREEN_HZ", "4"))
        self.interval = interval if interval is not None else max(0.05, 1.0 / configured_hz)
        self.trace = trace or (lambda message: None)
        self._latest: Optional[ScreenObservation] = None
        self._updates = 0
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def latest(self) -> Optional[ScreenObservation]:
        with self._condition:
            return self._latest

    @property
    def updates(self) -> int:
        with self._condition:
            return self._updates

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="tasker-screen-observer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def wait_for_update(
        self,
        previous: Optional[ScreenObservation],
        timeout: float,
    ) -> Optional[ScreenObservation]:
        previous_time = previous.captured_at if previous else 0.0
        deadline = _now() + timeout
        with self._condition:
            while _now() < deadline:
                if self._latest and self._latest.captured_at > previous_time:
                    return self._latest
                self._condition.wait(timeout=min(self.interval, max(0.01, deadline - _now())))
            return self._latest

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                observation = ScreenObservation.from_payload(self.capture())
                with self._condition:
                    self._latest = observation
                    self._updates += 1
                    self._condition.notify_all()
            except Exception as exc:
                self.trace("B_SCREEN_ERROR {}".format(exc))
            self._stop.wait(self.interval)


def handoff_matches(
    boundary: PredictedBoundary,
    before: Optional[ScreenObservation],
    after: Optional[ScreenObservation],
) -> bool:
    if after is None:
        return False
    if boundary.foreground_app and after.foreground_app:
        if boundary.foreground_app.lower() not in after.foreground_app.lower():
            return False
    if boundary.requires_visual_change and before and before.screen_hash and after.screen_hash:
        if before.screen_hash == after.screen_hash:
            return False
    return True


class DualLobeCoordinator:
    """Run A and B with a verified, bounded handoff.

    preview_fn must be stateless: it may call a model, but it must not commit
    actions or mutate task state.  commit_fn is called only after the batch
    has actually executed and the screen handoff has been accepted.
    """

    def __init__(
        self,
        preview_fn: Callable[[LobeBatch, PredictedBoundary, ScreenObservation], Optional[Dict[str, Any]]],
        commit_fn: Callable[[LobeBatch, ScreenObservation], bool],
        execute_fn: Callable[[Dict[str, Any]], None],
        capture_fn: Callable[[], Mapping[str, Any]],
        fallback_fn: Callable[[], Optional[Dict[str, Any]]],
        profile: str = PROFILE_SCREEN_AWARE,
        trace_fn: Optional[Callable[[str], None]] = None,
        preview_timeout: Optional[float] = None,
    ) -> None:
        if profile not in VALID_PROFILES:
            raise ValueError("unknown Tasker lobe-B profile: {}".format(profile))
        self.profile = profile
        self.preview_fn = preview_fn
        self.commit_fn = commit_fn
        self.execute_fn = execute_fn
        self.fallback_fn = fallback_fn
        self.trace_fn = trace_fn or (lambda message: None)
        self.preview_timeout = preview_timeout or float(os.getenv("TASKER_PREVIEW_TIMEOUT", "120"))
        self.observer = ScreenObserver(capture_fn, trace=self.trace_fn)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tasker-lobe-b")

    def _trace(self, report: DualLobeReport, message: str) -> None:
        report.trace.append(message)
        self.trace_fn(message)

    def run(self, initial_response: Dict[str, Any], max_batches: int = 20) -> DualLobeReport:
        report = DualLobeReport(
            status="running",
            batches_executed=0,
            actions_executed=0,
            lookahead_ready=0,
            lookahead_rejected=0,
            screen_updates=0,
        )
        self.observer.start()
        current_observation = self.observer.latest
        current = LobeBatch(
            batch_id=batch_id_for(initial_response, 1, "A"),
            source_lobe="A",
            response=initial_response,
            predicted_boundary=predict_boundary(
                initial_response,
                batch_id_for(initial_response, 1, "A"),
                current_observation,
            ),
            needs_commit=False,
        )

        try:
            for ordinal in range(1, max_batches + 1):
                before = self.observer.latest or current_observation
                self._trace(
                    report,
                    "A_EXEC_START batch={} actions={}".format(current.batch_id, current.action_count),
                )

                future: Optional[Future] = None
                if self.profile != PROFILE_OFF:
                    future = self.executor.submit(
                        self.preview_fn,
                        current,
                        current.predicted_boundary,
                        before or ScreenObservation(_now(), ""),
                    )
                    self._trace(
                        report,
                        "B_PREDICT_START base={} boundary={}".format(
                            current.batch_id,
                            current.predicted_boundary.expected_transition,
                        ),
                    )

                self.execute_fn(current.response)
                report.batches_executed += 1
                report.actions_executed += current.action_count

                after = self.observer.wait_for_update(before, timeout=2.0)
                report.screen_updates = self.observer.updates
                self._trace(
                    report,
                    "A_EXEC_DONE batch={} screen_hash_changed={}".format(
                        current.batch_id,
                        bool(before and after and before.screen_hash != after.screen_hash),
                    ),
                )

                if current.needs_commit:
                    if not after or not self.commit_fn(current, after):
                        report.status = "commit_failed"
                        self._trace(report, "HANDOFF_STOP commit_failed batch={}".format(current.batch_id))
                        break
                    self._trace(report, "B_COMMIT_OK batch={}".format(current.batch_id))

                if _has_terminal_action(current.response):
                    report.status = "completed"
                    break

                candidate_response: Optional[Dict[str, Any]] = None
                if future is not None:
                    try:
                        candidate_response = future.result(timeout=self.preview_timeout)
                        if candidate_response:
                            report.lookahead_ready += 1
                            self._trace(
                                report,
                                "B_PREDICT_READY base={}".format(current.batch_id),
                            )
                    except TimeoutError:
                        self._trace(report, "B_PREDICT_TIMEOUT base={}".format(current.batch_id))
                    except Exception as exc:
                        self._trace(report, "B_PREDICT_ERROR {}".format(exc))

                candidate_boundary = None
                if candidate_response:
                    candidate_id = batch_id_for(candidate_response, ordinal + 1, "B")
                    candidate_boundary = predict_boundary(candidate_response, candidate_id, after)
                    if self.profile == PROFILE_PREDICTIVE:
                        accepted = bool(after)
                    else:
                        accepted = handoff_matches(current.predicted_boundary, before, after)
                    if not accepted:
                        report.lookahead_rejected += 1
                        candidate_response = None
                        self._trace(
                            report,
                            "B_HANDOFF_REJECT base={} reason=boundary_not_observed".format(current.batch_id),
                        )

                if candidate_response is None:
                    candidate_response = self.fallback_fn()
                    if not candidate_response:
                        report.status = "waiting_for_next_step"
                        break
                    candidate_id = batch_id_for(candidate_response, ordinal + 1, "A")
                    candidate_boundary = predict_boundary(candidate_response, candidate_id, after)
                    source_lobe = "A-FALLBACK"
                    needs_commit = False
                    self._trace(report, "A_FALLBACK_ACCEPT batch={}".format(candidate_id))
                else:
                    source_lobe = "B"
                    needs_commit = True

                current = LobeBatch(
                    batch_id=candidate_id,
                    source_lobe=source_lobe,
                    response=candidate_response,
                    predicted_boundary=candidate_boundary,
                    needs_commit=needs_commit,
                )

            if report.status == "running":
                report.status = "max_batches"
        finally:
            report.screen_updates = self.observer.updates
            self.observer.stop()
            self.executor.shutdown(wait=False, cancel_futures=True)
        return report


def _has_terminal_action(response: Mapping[str, Any]) -> bool:
    return any(
        isinstance(action, Mapping)
        and action.get("action") in {"task_completed", "subtask_failed"}
        for action in response.get("actions", [])
    )
