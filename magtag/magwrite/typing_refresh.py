"""Host-safe newest-snapshot-only physical refresh coordinator."""

from magwrite.single_line import MAX_PARTIAL_REFRESHES


class RefreshStopped(Exception):
    pass


class TypingRefreshCoordinator:
    def __init__(
        self,
        adapter,
        logger,
        monotonic,
        full_refresh_interval=50,
        timeout_seconds=20.0,
    ):
        self.adapter = adapter
        self.logger = logger
        self.monotonic = monotonic
        self.full_refresh_interval = full_refresh_interval
        self.timeout_seconds = timeout_seconds
        self.latest = None
        self.inflight_revision = None
        self.displayed_revision = -1
        self.inflight_started = None
        self.inflight_full = False
        self.partial_refreshes = 0
        self.full_refreshes = 0
        self.stale_frames_skipped = 0
        self.catch_up_refreshes = 0
        self.timeouts = 0
        self.partial_durations = []

    def offer(self, framebuffer, render_revision, document_revision, scenario):
        if self.latest is not None:
            previous = self.latest[1]
            if previous not in (self.displayed_revision, self.inflight_revision):
                self.stale_frames_skipped += 1
        self.latest = (
            bytearray(framebuffer),
            render_revision,
            document_revision,
            scenario,
        )

    @property
    def caught_up(self):
        return (
            self.latest is not None
            and self.inflight_revision is None
            and self.displayed_revision == self.latest[1]
        )

    def _start_latest(self, queue_depth):
        framebuffer, revision, document_revision, scenario = self.latest
        total_refreshes = self.partial_refreshes + self.full_refreshes
        request_full = total_refreshes == 0 or (
            total_refreshes > 0
            and total_refreshes % self.full_refresh_interval == 0
        )
        if not request_full and self.partial_refreshes >= MAX_PARTIAL_REFRESHES:
            raise RefreshStopped("100-partial-refresh safety limit reached")
        started = self.monotonic()
        actual_full = self.adapter.begin_refresh(framebuffer, full=request_full)
        self.inflight_revision = revision
        self.inflight_started = started
        self.inflight_full = actual_full
        self.logger(
            {
                "event": "refresh_started",
                "scenario": scenario,
                "revision": revision,
                "document_revision": document_revision,
                "mode": "full" if actual_full else "partial",
                "queue_depth": queue_depth,
            }
        )

    def service(self, queue_depth=0):
        now = self.monotonic()
        if self.inflight_revision is not None:
            if self.adapter.is_busy():
                if now - self.inflight_started > self.timeout_seconds:
                    self.timeouts += 1
                    raise RefreshStopped("display busy timeout")
                return
            revision = self.inflight_revision
            duration_ms = int((now - self.inflight_started) * 1000)
            was_full = self.inflight_full
            self.inflight_revision = None
            self.displayed_revision = revision
            if was_full:
                self.full_refreshes += 1
            else:
                self.partial_refreshes += 1
                self.partial_durations.append(duration_ms)
            latest_revision = self.latest[1]
            stale = revision != latest_revision
            self.logger(
                {
                    "event": "refresh_completed",
                    "scenario": self.latest[3],
                    "revision": revision,
                    "duration_ms": duration_ms,
                    "latest_render_revision": latest_revision,
                    "stale_on_completion": stale,
                }
            )
            if stale:
                self.catch_up_refreshes += 1
                self.logger(
                    {
                        "event": "catch_up_scheduled",
                        "from_revision": revision,
                        "to_revision": latest_revision,
                    }
                )

        if (
            self.inflight_revision is None
            and self.latest is not None
            and self.displayed_revision != self.latest[1]
        ):
            self._start_latest(queue_depth)
