"""Drain-first, single-refresh-in-flight UART viewport scheduler."""


class TransportStopped(Exception):
    pass


class TransportScheduler:
    def __init__(self, parser, receiver, display, render, max_frames_per_service=16):
        self.parser = parser
        self.receiver = receiver
        self.display = display
        self.render = render
        self.max_frames_per_service = max_frames_per_service
        self.inflight_revision = None
        self.displayed_revision = 0
        self.rendered = 0
        self.stopped = False

    def service(self, chunks=()):
        if self.stopped:
            return
        for chunk in chunks:
            self.parser.feed(chunk)
        for _ in range(self.max_frames_per_service):
            frame = self.parser.pop()
            if frame is None:
                break
            self.receiver.accept(frame)
        if self.inflight_revision is not None and not self.display.is_busy():
            self.displayed_revision = self.inflight_revision
            self.inflight_revision = None
        if self.inflight_revision is None:
            viewport = self.receiver.take_pending()
            if viewport is not None:
                if viewport.revision > self.receiver.latest_revision:
                    raise TransportStopped("display revision exceeds received revision")
                self.display.begin_refresh(self.render(viewport), full=self.rendered == 0)
                self.inflight_revision = viewport.revision
                self.rendered += 1

    def stop(self):
        self.stopped = True
