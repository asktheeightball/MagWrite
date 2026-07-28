"""Bounded orchestration for the one-full-plus-20-partial physical test."""


PARTIAL_UPDATE_COUNT = 20


class PhysicalRefreshTest:
    def __init__(
        self,
        adapter,
        render_frame,
        guard,
        logger,
        monotonic,
        timeout_seconds=20.0,
    ):
        self.adapter = adapter
        self.render_frame = render_frame
        self.guard = guard
        self.logger = logger
        self.monotonic = monotonic
        self.timeout_seconds = timeout_seconds

    def _refresh(self, index, mode, framebuffer):
        started = self.monotonic()
        actual_full = self.adapter.begin_refresh(
            framebuffer, full=(mode == "full")
        )
        idle = self.adapter.wait_until_idle(self.timeout_seconds)
        duration_ms = int((self.monotonic() - started) * 1000)
        record = {
            "event": "physical_refresh",
            "index": index,
            "mode": "full" if actual_full else "partial",
            "duration_ms": duration_ms,
            "timeout": not idle,
        }
        self.logger(record)
        return idle, duration_ms, actual_full

    def run(self):
        if not self.guard.claim():
            raise RuntimeError("physical test guard already exists; refusing rerun")

        partial_durations = []
        full_duration = None
        completed = 0
        timeouts = 0
        try:
            self.adapter.initialize()
        except Exception as error:
            self.logger(
                {"event": "physical_test_error", "stage": "initialize",
                 "detail": str(error)}
            )
            raise

        framebuffer = self.render_frame(0)
        idle, full_duration, actual_full = self._refresh(
            1, "full", framebuffer
        )
        if not actual_full:
            raise RuntimeError("initial refresh was not full")
        if not idle:
            timeouts = 1
            return self._summary(full_duration, partial_durations, completed, timeouts)

        for partial_index in range(1, PARTIAL_UPDATE_COUNT + 1):
            framebuffer = self.render_frame(partial_index)
            idle, duration, actual_full = self._refresh(
                partial_index + 1, "partial", framebuffer
            )
            if actual_full:
                raise RuntimeError("controlled partial update unexpectedly forced full")
            if not idle:
                timeouts += 1
                break
            partial_durations.append(duration)
            completed += 1

        summary = self._summary(
            full_duration, partial_durations, completed, timeouts
        )
        if completed == PARTIAL_UPDATE_COUNT and not timeouts:
            self.guard.complete(summary)
            completion_record = {"event": "physical_test_complete"}
            completion_record.update(summary)
            self.logger(completion_record)
        else:
            stopped_record = {"event": "physical_test_stopped"}
            stopped_record.update(summary)
            self.logger(stopped_record)
        return summary

    def _summary(self, full_duration, partial_durations, completed, timeouts):
        count = len(partial_durations)
        return {
            "initial_full_duration_ms": full_duration,
            "partial_min_ms": min(partial_durations) if count else None,
            "partial_max_ms": max(partial_durations) if count else None,
            "partial_mean_ms": (
                sum(partial_durations) // count if count else None
            ),
            "timeout_count": timeouts,
            "completed_partial_updates": completed,
            "final_displayed_revision": completed,
            "final_document_revision": completed,
        }
