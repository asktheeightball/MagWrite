"""Bounded one-shot sender independent of CircuitPython UART construction."""

from magwrite_transport.deterministic_viewports import deterministic_messages
from magwrite_transport.protocol import END_OF_SCENARIO, encode_frame


class UartSender:
    def __init__(self, uart, logger):
        self.uart = uart
        self.logger = logger
        self.bytes_sent = 0
        self.frames_sent = 0

    def run(self, sleep, delay_seconds, scenario_delay_seconds=None):
        if scenario_delay_seconds is None:
            scenario_delay_seconds = delay_seconds
        for sequence, (kind, revision, payload) in enumerate(deterministic_messages(), 1):
            frame = encode_frame(kind, sequence, revision, payload)
            self.uart.write(frame)
            self.bytes_sent += len(frame)
            self.frames_sent += 1
            self.logger({"event": "uart_frame_sent", "sequence": sequence, "revision": revision,
                         "message_type": kind, "payload_bytes": len(payload), "frame_bytes": len(frame)})
            sleep(scenario_delay_seconds if kind == END_OF_SCENARIO else delay_seconds)
