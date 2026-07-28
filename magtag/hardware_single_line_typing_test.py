"""One-run, locally generated single-line physical typing feasibility test."""

import json
import math
import os
import storage
import supervisor
import time

import config
from magwrite.display_adapter import validate_physical_test_activation
from magwrite.events import BoundedEventQueue, QueueOverflow
from magwrite.mono_canvas import MonoCanvas
from magwrite.serial_log import StructuredSerialLogger
from magwrite.single_line import (
    MAX_TYPING_EVENTS,
    EditRejected,
    HorizontalViewport,
    ScheduledScenarioProducer,
    SequenceTracker,
    SingleLineEditor,
    TYPING_COMPLETE_GUARD,
    TYPING_START_GUARD,
    numbered_scenarios,
)
from magwrite.test_pattern import draw_text, landscape_rect
from magwrite.typing_refresh import RefreshStopped, TypingRefreshCoordinator
from magwrite.uc8151_adapter import UC8151DisplayAdapter, UPSTREAM_COMMIT


def path_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


class PersistentGuard:
    def claim(self):
        if path_exists(TYPING_START_GUARD) or path_exists(TYPING_COMPLETE_GUARD):
            return False
        with open(TYPING_START_GUARD, "w") as handle:
            handle.write("claimed\n")
        return True

    def complete(self, summary):
        with open(TYPING_COMPLETE_GUARD, "w") as handle:
            handle.write(json.dumps(summary))

    def fail(self, summary):
        # Keep the rerun-blocking start guard while making the stop reason
        # recoverable even if the USB serial monitor disconnects.
        with open(TYPING_START_GUARD, "w") as handle:
            handle.write(json.dumps(summary))


def render_frame(editor, viewport, document_revision, render_revision, inflight, shown):
    canvas = MonoCanvas()
    draw_text(canvas, "MAGWRITE TYPE TEST", 114, 8, 1)
    landscape_rect(canvas, 8, 23, 280, 1, 1)
    view = viewport.snapshot(editor)
    draw_text(canvas, view["text"], 10, 42, 2)
    cursor_x = 10 + view["cursor_cell"] * 8
    landscape_rect(canvas, cursor_x, 54, 6, 2, 1)
    landscape_rect(canvas, 8, 68, 280, 1, 1)
    draw_text(canvas, "DOC %04d" % document_revision, 8, 83, 1)
    draw_text(canvas, "INFLIGHT %04d" % max(0, inflight), 89, 83, 1)
    draw_text(canvas, "SHOWN %04d" % max(0, shown), 211, 83, 1)
    landscape_rect(canvas, 8, 101, 280, 1, 1)
    return canvas.buf


def timing_summary(values):
    if not values:
        return {"min_ms": None, "max_ms": None, "mean_ms": None, "stddev_ms": None}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "min_ms": min(values),
        "max_ms": max(values),
        "mean_ms": round(mean, 1),
        "stddev_ms": round(math.sqrt(variance), 1),
    }


time.sleep(3)
logger = StructuredSerialLogger()
mode = config.PHYSICAL_TEST_MODE
logger(
    {
        "event": "typing_test_boot",
        "activation": config.ENABLE_PHYSICAL_DISPLAY,
        "test_mode": mode,
        "decision": config.HARDWARE_COMPATIBILITY_DECISION,
        "controller": config.DISPLAY_CONTROLLER,
        "upstream_commit": UPSTREAM_COMMIT,
    }
)

try:
    validate_physical_test_activation(config, mode)
except Exception as error:
    logger({"event": "typing_test_refused", "detail": str(error)})
    while True:
        time.sleep(3600)

supervisor.runtime.autoreload = False
guard = PersistentGuard()
if not guard.claim():
    raise RuntimeError("typing-test guard exists; refusing rerun")

adapter = UC8151DisplayAdapter(config, mode)
adapter.initialize()
refresh = TypingRefreshCoordinator(
    adapter,
    logger,
    time.monotonic,
    full_refresh_interval=config.FULL_REFRESH_INTERVAL,
)
queue = BoundedEventQueue(config.EVENT_QUEUE_CAPACITY)
tracker = SequenceTracker()
viewport = HorizontalViewport(columns=34)
global_document_revision = 0
global_render_revision = 0
events_generated = 0
events_rejected = 0
queue_max_depth = 0
scenario_results = {}
result = "PASS"
stop_reason = None

try:
    blank = SingleLineEditor(max_chars=96)
    refresh.offer(
        render_frame(blank, viewport, 0, 0, -1, -1),
        0,
        0,
        "initial",
    )
    while not refresh.caught_up:
        refresh.service()
        time.sleep(0.005)
    logger({"event": "checkpoint_wait", "scenario": "initial"})
    if input("Type CONTINUE or STOP: ").strip().upper() != "CONTINUE":
        raise RefreshStopped("visual stop at initial frame")

    for name, wpm, events, expected in numbered_scenarios():
        editor = SingleLineEditor(max_chars=96)
        producer = ScheduledScenarioProducer(
            events, wpm, start_ms=time.monotonic() * 1000
        )
        logger(
            {
                "event": "scenario_started",
                "scenario": name,
                "wpm": wpm,
                "event_count": len(events),
            }
        )
        while not producer.complete or len(queue) or not refresh.caught_up:
            now_ms = time.monotonic() * 1000
            try:
                generated = producer.produce_due(now_ms, queue)
            except QueueOverflow:
                raise RefreshStopped("queue overflow")
            events_generated += generated
            queue_max_depth = max(queue_max_depth, len(queue))
            event = queue.get()
            while event is not None:
                tracker.accept(event)
                try:
                    changed = editor.apply(event)
                except EditRejected:
                    events_rejected += 1
                    raise RefreshStopped("unexpected rejected edit")
                if changed:
                    global_document_revision += 1
                global_render_revision += 1
                logger(
                    {
                        "event": "key_processed",
                        "scenario": name,
                        "sequence": event.sequence,
                        "key": event.value or event.kind,
                        "document_revision": global_document_revision,
                        "render_revision": global_render_revision,
                        "queue_depth": len(queue),
                    }
                )
                frame = render_frame(
                    editor,
                    viewport,
                    global_document_revision,
                    global_render_revision,
                    refresh.inflight_revision or -1,
                    refresh.displayed_revision,
                )
                refresh.offer(
                    frame,
                    global_render_revision,
                    global_document_revision,
                    name,
                )
                event = queue.get()
            refresh.service(len(queue))
            time.sleep(0.005)

        if editor.text != expected:
            raise RefreshStopped("final text mismatch in " + name)
        if refresh.displayed_revision != global_render_revision:
            raise RefreshStopped("display failed to catch up in " + name)
        scenario_results[name] = editor.text
        logger(
            {
                "event": "scenario_complete",
                "scenario": name,
                "final_text": editor.text,
                "document_revision": global_document_revision,
                "render_revision": global_render_revision,
                "displayed_revision": refresh.displayed_revision,
            }
        )
        logger({"event": "checkpoint_wait", "scenario": name})
        if input("Type CONTINUE or STOP: ").strip().upper() != "CONTINUE":
            raise RefreshStopped("visual stop after " + name)

except Exception as error:
    result = "FAIL"
    stop_reason = str(error)

summary = {
    "event": "typing_test_summary",
    "result": result,
    "stop_reason": stop_reason,
    "events_generated": events_generated,
    "events_processed": tracker.processed,
    "events_rejected": events_rejected,
    "queue_max_depth": queue_max_depth,
    "queue_overflows": queue.overflow_count,
    "document_revision": global_document_revision,
    "render_revision": global_render_revision,
    "inflight_revision": refresh.inflight_revision,
    "displayed_revision": refresh.displayed_revision,
    "partial_refreshes": refresh.partial_refreshes,
    "full_refreshes": refresh.full_refreshes,
    "stale_frames_skipped": refresh.stale_frames_skipped,
    "catch_up_refreshes": refresh.catch_up_refreshes,
    "timeouts": refresh.timeouts,
    "timing": timing_summary(refresh.partial_durations),
    "scenarios": scenario_results,
}
logger(summary)
if result == "PASS" and events_generated <= MAX_TYPING_EVENTS:
    guard.complete(summary)
else:
    guard.fail(summary)
try:
    storage.remount("/", readonly=True)
except RuntimeError as error:
    logger({"event": "filesystem_remount_warning", "detail": str(error)})
while True:
    time.sleep(3600)
