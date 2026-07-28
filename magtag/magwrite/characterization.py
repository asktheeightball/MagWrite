"""Bounded, checkpoint-gated 50/100-update characterization runner."""

import math

from magwrite.display_adapter import REFRESH_50_MODE, REFRESH_100_MODE


TEST_SPECS = {
    REFRESH_50_MODE: {
        "test": "refresh_50",
        "updates": 50,
        "checkpoints": (0, 10, 20, 30, 40, 50),
    },
    REFRESH_100_MODE: {
        "test": "refresh_100",
        "updates": 100,
        "checkpoints": (0, 20, 40, 60, 80, 100),
    },
}

KNOWN_GUARDS = {
    "UC8151_20_UPDATE": (
        "/magwrite_refresh_test_20.started",
        "/magwrite_refresh_test_20.complete",
    ),
    REFRESH_50_MODE: (
        "/magwrite_refresh_test_50.started",
        "/magwrite_refresh_test_50.complete",
    ),
    REFRESH_100_MODE: (
        "/magwrite_refresh_test_100.started",
        "/magwrite_refresh_test_100.complete",
    ),
}

REFRESH_50_PASS_GUARD = "/magwrite_refresh_test_50.pass"


def guard_paths(mode):
    try:
        return KNOWN_GUARDS[mode]
    except KeyError:
        raise ValueError("unknown physical test mode")


def require_test_prerequisite(mode, prerequisite_passed):
    if mode == REFRESH_100_MODE and not prerequisite_passed:
        raise RuntimeError("REFRESH_100 requires recorded REFRESH_50 PASS")


class TimingSafety:
    def __init__(self):
        self.durations = []
        self.consecutive_over_1000 = 0

    def add(self, duration_ms):
        self.durations.append(duration_ms)
        if duration_ms > 1500:
            return "partial refresh exceeded 1500 ms"
        if duration_ms > 1000:
            self.consecutive_over_1000 += 1
        else:
            self.consecutive_over_1000 = 0
        if self.consecutive_over_1000 >= 3:
            return "three consecutive partial refreshes exceeded 1000 ms"
        if len(self.durations) >= 20:
            first = self.durations[:10]
            recent = self.durations[-10:]
            first_mean = sum(first) / 10.0
            recent_mean = sum(recent) / 10.0
            if recent_mean > first_mean * 1.25 and recent_mean - first_mean > 100:
                return "partial-refresh timing drift exceeded 25 percent"
        return None

    def summary(self):
        values = self.durations
        if not values:
            return {
                "partial_min_ms": None,
                "partial_max_ms": None,
                "partial_mean_ms": None,
                "partial_median_ms": None,
                "partial_stddev_ms": None,
                "timing_drift_ms": None,
            }
        ordered = sorted(values)
        count = len(values)
        mean = sum(values) / count
        middle = count // 2
        if count % 2:
            median = ordered[middle]
        else:
            median = (ordered[middle - 1] + ordered[middle]) / 2
        variance = sum((value - mean) ** 2 for value in values) / count
        drift = None
        if count >= 20:
            drift = (sum(values[-10:]) / 10.0) - (sum(values[:10]) / 10.0)
        return {
            "partial_min_ms": min(values),
            "partial_max_ms": max(values),
            "partial_mean_ms": round(mean, 1),
            "partial_median_ms": round(median, 1),
            "partial_stddev_ms": round(math.sqrt(variance), 1),
            "timing_drift_ms": round(drift, 1) if drift is not None else None,
        }


class CharacterizationTest:
    def __init__(
        self,
        mode,
        adapter,
        render_frame,
        guard,
        logger,
        monotonic,
        checkpoint,
        prerequisite_passed=False,
        timeout_seconds=20.0,
    ):
        if mode not in TEST_SPECS:
            raise ValueError("unsupported characterization mode")
        self.mode = mode
        self.spec = TEST_SPECS[mode]
        self.adapter = adapter
        self.render_frame = render_frame
        self.guard = guard
        self.logger = logger
        self.monotonic = monotonic
        self.checkpoint = checkpoint
        self.prerequisite_passed = prerequisite_passed
        self.timeout_seconds = timeout_seconds

    def _refresh(self, index, full):
        framebuffer = self.render_frame(index, self.spec["updates"])
        started = self.monotonic()
        actual_full = self.adapter.begin_refresh(framebuffer, full=full)
        idle = self.adapter.wait_until_idle(self.timeout_seconds)
        duration_ms = int((self.monotonic() - started) * 1000)
        record = {
            "event": "physical_refresh",
            "test": self.spec["test"],
            "index": index,
            "mode": "full" if actual_full else "partial",
            "duration_ms": duration_ms,
            "timeout": not idle,
            "displayed_pattern_revision": index,
            "cumulative_partial_updates": index,
            "busy_anomaly": False,
        }
        self.logger(record)
        return idle, duration_ms, actual_full

    def run(self):
        require_test_prerequisite(self.mode, self.prerequisite_passed)
        if not self.guard.claim():
            raise RuntimeError("test-specific guard exists; refusing rerun")

        self.adapter.initialize()
        timing = TimingSafety()
        stop_reason = None
        timeouts = 0
        completed = 0

        idle, full_duration, actual_full = self._refresh(0, True)
        if not actual_full:
            raise RuntimeError("initial seed was not full")
        if not idle:
            timeouts = 1
            stop_reason = "busy timeout during initial full refresh"
        elif not self.checkpoint(self.spec["test"], 0):
            stop_reason = "visual stop at initial full checkpoint"

        if stop_reason is None:
            for index in range(1, self.spec["updates"] + 1):
                idle, duration, actual_full = self._refresh(index, False)
                if actual_full:
                    stop_reason = "unexpected full refresh during partial sequence"
                    break
                if not idle:
                    timeouts += 1
                    stop_reason = "busy timeout at partial update %d" % index
                    break
                completed = index
                stop_reason = timing.add(duration)
                if stop_reason:
                    break
                if index in self.spec["checkpoints"]:
                    if not self.checkpoint(self.spec["test"], index):
                        stop_reason = "visual stop at update %d" % index
                        break

        summary = {
            "test": self.spec["test"],
            "initial_full_duration_ms": full_duration,
            "timeout_count": timeouts,
            "completed_partial_updates": completed,
            "final_displayed_revision": completed,
            "stop_reason": stop_reason,
        }
        summary.update(timing.summary())
        if completed == self.spec["updates"] and stop_reason is None:
            self.guard.complete(summary)
            record = {"event": "physical_test_complete"}
        else:
            record = {"event": "physical_test_stopped"}
        record.update(summary)
        self.logger(record)
        return summary
