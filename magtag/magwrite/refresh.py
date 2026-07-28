"""Cooperative asynchronous refresh scheduling."""


class RefreshCoordinator:
    def __init__(self, display, renderer, full_refresh_interval=50, logger=None):
        if full_refresh_interval < 1:
            raise ValueError("full_refresh_interval must be positive")
        self.display = display
        self.renderer = renderer
        self.full_refresh_interval = full_refresh_interval
        self.logger = logger
        self.displayed_revision = -1
        self.inflight_revision = None
        self.event_count = 0
        self.stale_frame_count = 0
        self.full_refresh_count = 0
        self.refresh_count = 0

    def _log(self, event, **fields):
        if self.logger:
            fields["event"] = event
            self.logger(fields)

    def note_event(self, document_revision):
        self.event_count += 1
        self._log("key_accepted", event_count=self.event_count,
                  document_revision=document_revision,
                  displayed_revision=self.displayed_revision)

    def service(self, now_ms, editor):
        completion = self.display.poll(now_ms)
        if completion is not None:
            revision, duration_ms, was_full = completion
            self.displayed_revision = revision
            self.inflight_revision = None
            self.refresh_count += 1
            if was_full:
                self.full_refresh_count += 1
            stale = self.displayed_revision != editor.revision
            if stale:
                self.stale_frame_count += 1
            self._log("refresh_end", event_count=self.event_count,
                      document_revision=editor.revision,
                      displayed_revision=self.displayed_revision,
                      refresh_duration_ms=duration_ms,
                      stale_frame_count=self.stale_frame_count,
                      full_refresh_count=self.full_refresh_count)

        if self.inflight_revision is None and self.displayed_revision != editor.revision:
            snapshot = self.renderer.snapshot(editor)
            full = self.refresh_count == 0 or (
                self.refresh_count % self.full_refresh_interval == 0
            )
            self.display.start(snapshot, full, now_ms)
            self.inflight_revision = snapshot.revision
            self._log("refresh_start", event_count=self.event_count,
                      document_revision=editor.revision,
                      displayed_revision=self.displayed_revision,
                      refresh_revision=snapshot.revision,
                      stale_frame_count=self.stale_frame_count,
                      full_refresh_count=self.full_refresh_count,
                      full=full)


class SimulatedAsyncDisplay:
    """Bounded one-frame display model used only by host tests."""

    def __init__(self, duration_ms=300):
        self.duration_ms = duration_ms
        self._active = None
        self.started = []

    def start(self, snapshot, full, now_ms):
        if self._active is not None:
            raise RuntimeError("display busy")
        self._active = (snapshot.revision, now_ms, full)
        self.started.append((snapshot.revision, full))

    def poll(self, now_ms):
        if self._active is None:
            return None
        revision, started_ms, full = self._active
        if now_ms - started_ms < self.duration_ms:
            return None
        self._active = None
        return revision, now_ms - started_ms, full
