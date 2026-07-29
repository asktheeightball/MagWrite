"""Deterministic host simulation of the Fruit Jam editor over the UART link.

The simulation proves scheduling, protocol, and acknowledgement behaviour only.
It does not and cannot prove physical e-paper behaviour.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if os.path.join(ROOT, "magtag") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "magtag"))
if os.path.join(ROOT, "fruitjam") not in sys.path:
    sys.path.append(os.path.join(ROOT, "fruitjam"))

from magwrite.ack_scheduler import AckDisplayScheduler
from magwrite.status_queue import StatusQueue
from magwrite.uart_protocol import FrameParser as InputParser
from magwrite.viewport_renderer import render_viewport
from magwrite_transport.editor_session import EditorSession

STEP_SECONDS = 0.005
FULL_REFRESH_SECONDS = 3.6
PARTIAL_REFRESH_SECONDS = 0.97


class SimulatedClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class SimulatedPanel:
    """Models one refresh in flight with a measured busy duration."""

    def __init__(self, clock, full=FULL_REFRESH_SECONDS,
                 partial=PARTIAL_REFRESH_SECONDS):
        self.clock = clock
        self.full_seconds = full
        self.partial_seconds = partial
        self.busy_until = None
        self.starts = []
        self.concurrent = 0
        self.maximum_concurrent = 0

    def begin_refresh(self, framebuffer, full=False):
        if self.busy_until is not None:
            raise RuntimeError("second physical refresh in flight")
        self.busy_until = self.clock.now + (
            self.full_seconds if full else self.partial_seconds
        )
        self.concurrent = 1
        self.maximum_concurrent = max(self.maximum_concurrent, 1)
        self.starts.append(full)
        return full

    def is_busy(self):
        if self.busy_until is None:
            return False
        if self.clock.now < self.busy_until:
            return True
        self.busy_until = None
        self.concurrent = 0
        return False


class EditorLink:
    """Wires one Fruit Jam session to one display-only MagTag scheduler."""

    def __init__(self, log=None, render=render_viewport, panel=None,
                 status_queue_capacity=32, **session_options):
        self.clock = SimulatedClock()
        self.records = []
        self.log = log if log is not None else self.records.append
        self.panel = panel or SimulatedPanel(self.clock)
        self.outbox = StatusQueue(status_queue_capacity)
        self.scheduler = AckDisplayScheduler(
            InputParser(), self.panel, render, self.outbox, self.clock
        )
        self.session = EditorSession(self.clock, self.log, **session_options)
        self.status_frames_sent = 0
        self.iterations = 0

    def step(self):
        self.iterations += 1
        self.session.service()
        chunks = self.session.take_outbound()
        self.scheduler.service(chunks)
        while len(self.outbox):
            item = self.outbox.pop()
            self.status_frames_sent += 1
            self.session.feed(item[3])
        self.clock.now += STEP_SECONDS

    def run(self, maximum_iterations=80000):
        while not self.session.complete:
            if self.iterations >= maximum_iterations:
                raise RuntimeError("editor simulation did not converge")
            self.step()
        return self
