"""Unguarded, read-only wired USB keyboard probe for the Fruit Jam.

Run from the serial REPL only, with every physical-test gate still DISABLED.
This module deliberately does the least that can still answer one question:
does a real wired USB keyboard deliver non-zero HID boot reports into the
already-implemented adapter?

It therefore:

* creates no guard file and writes nothing to the device filesystem;
* never touches the display;
* never constructs the editor, the viewport builder, or the UART transport;
* bounds every loop and every diagnostic burst.

Descriptor reading, interface selection, endpoint claiming, and report reading
all go through the shipped ``usb_host_backend`` and ``usb_hid_descriptors``
modules rather than a parallel implementation, so a PASS here is evidence about
the real code path and not about the probe.
"""

try:
    import json
except ImportError:
    import ujson as json

import time

from magwrite_transport import hid_keymap
from magwrite_transport.usb_hid_descriptors import (
    UsbKeyboardError, parse_configuration, select_boot_keyboard,
)
from magwrite_transport.usb_host_backend import UsbHostKeyboardBackend

PROBE_SECONDS = 90
MAX_REPORTS_LOGGED = 60
HEARTBEAT_SECONDS = 10.0
READ_TIMEOUT_MS = 2

# The five sample keys the probe wants to see before it can stop early. Shift+A
# is tracked separately from A because the shifted variant is what proves the
# modifier byte reaches the keymap.
TARGET_A = 0x04
TARGET_ENTER = 0x28
TARGET_BACKSPACE = 0x2A
TARGET_LEFT = 0x50
TARGETS = ("a", "shift_a", "enter", "backspace", "left")


def emit(event, **fields):
    fields["event"] = event
    print(json.dumps(fields, separators=(",", ":")))


def _text(device, attribute):
    try:
        return getattr(device, attribute)
    except Exception:
        return None


def survey(backend):
    """Dump every attached device's identity and configuration descriptor."""
    try:
        import usb.core as usb_core
    except ImportError as error:
        emit("probe_host_unavailable", detail=str(error))
        return False
    try:
        devices = list(usb_core.find(find_all=True))
    except Exception as error:
        emit("probe_enumeration_failed", detail=str(error))
        return False
    emit("probe_enumeration", device_count=len(devices))
    if not devices:
        return False
    for index, device in enumerate(devices):
        emit(
            "probe_device", index=index,
            vendor_id="%04X" % device.idVendor,
            product_id="%04X" % device.idProduct,
            manufacturer=_text(device, "manufacturer"),
            product=_text(device, "product"),
            serial_number=_text(device, "serial_number"),
            speed=_text(device, "speed"),
        )
        try:
            raw = backend._read_configuration(device)
        except Exception as error:
            emit("probe_descriptor_error", index=index, detail=str(error))
            continue
        emit(
            "probe_configuration_descriptor", index=index, length=len(raw),
            hex="".join("%02X" % byte for byte in raw),
        )
        try:
            interfaces = parse_configuration(raw)
        except Exception as error:
            emit("probe_parse_error", index=index, detail=str(error))
            continue
        for interface in interfaces:
            emit("probe_interface", index=index, detail=interface.describe())
        try:
            interface, endpoint = select_boot_keyboard(interfaces)
        except UsbKeyboardError as error:
            emit("probe_selection_error", index=index, detail=str(error))
            continue
        emit(
            "probe_selected", index=index, interface=interface.number,
            interface_class=interface.interface_class,
            interface_subclass=interface.subclass,
            interface_protocol=interface.protocol,
            endpoint="0x%02X" % endpoint.address,
            max_packet_size=endpoint.max_packet_size,
            interval=endpoint.interval,
        )
        # CircuitPython's built-in host keyboard driver routes an attached
        # keyboard to the serial console. If it still owns the interface here,
        # every keypress goes to stdin instead of our interrupt endpoint, so
        # the detach performed by ``_claim`` is the decisive step.
        try:
            active = device.is_kernel_driver_active(interface.number)
        except Exception as error:
            active = "unknown: " + str(error)
        emit(
            "probe_kernel_driver", index=index, interface=interface.number,
            active=active, phase="before_claim",
        )
    return True


def decode(report):
    """Translate one boot report the way the shipped adapter would."""
    modifier = report[0]
    shift = hid_keymap.shift_active(modifier)
    keys = []
    for usage in report[2:8]:
        if usage == hid_keymap.USAGE_NONE:
            continue
        entry = {"usage": "0x%02X" % usage}
        if hid_keymap.is_error_usage(usage):
            entry["kind"] = "ERROR"
        elif hid_keymap.is_modifier_usage(usage):
            entry["kind"] = "MODIFIER"
        else:
            translated = hid_keymap.translate(usage, shift, False)
            if translated is None:
                entry["kind"] = "UNSUPPORTED"
            else:
                entry["kind"] = translated[0]
                if translated[1]:
                    entry["value"] = translated[1]
        keys.append(entry)
    return modifier, shift, keys


def poll(backend, seconds=PROBE_SECONDS):
    """Read the interrupt endpoint until the sample keys appear or time runs out."""
    counts = {
        "reports": 0, "idle_polls": 0, "zero_reports": 0,
        "nonzero_reports": 0, "duplicate_reports": 0, "release_reports": 0,
        "error_reports": 0, "unsupported_usages": 0,
    }
    seen = {name: False for name in TARGETS}
    logged = 0
    previous = None
    started = time.monotonic()
    deadline = started + seconds
    heartbeat = started + HEARTBEAT_SECONDS
    stop_reason = "timeout"

    while True:
        now = time.monotonic()
        if now >= deadline:
            break
        if now >= heartbeat:
            heartbeat = now + HEARTBEAT_SECONDS
            emit(
                "probe_waiting", elapsed=round(now - started, 1),
                reports=counts["reports"], nonzero=counts["nonzero_reports"],
                remaining=[name for name in TARGETS if not seen[name]],
            )
        try:
            report = backend.read_report()
        except UsbKeyboardError as error:
            emit("probe_disconnected", detail=str(error))
            stop_reason = "disconnected"
            break
        if report is None:
            counts["idle_polls"] += 1
            continue
        counts["reports"] += 1
        if report == previous:
            counts["duplicate_reports"] += 1
            continue
        previous = report

        modifier, shift, keys = decode(report)
        if modifier == 0 and not keys:
            counts["zero_reports"] += 1
            counts["release_reports"] += 1
        else:
            counts["nonzero_reports"] += 1
        for entry in keys:
            if entry["kind"] == "ERROR":
                counts["error_reports"] += 1
            elif entry["kind"] == "UNSUPPORTED":
                counts["unsupported_usages"] += 1

        for usage in report[2:8]:
            if usage == TARGET_A:
                seen["shift_a" if shift else "a"] = True
            elif usage == TARGET_ENTER:
                seen["enter"] = True
            elif usage == TARGET_BACKSPACE:
                seen["backspace"] = True
            elif usage == TARGET_LEFT:
                seen["left"] = True

        if logged < MAX_REPORTS_LOGGED:
            logged += 1
            emit(
                "probe_report", index=counts["reports"],
                raw="".join("%02X" % byte for byte in report),
                modifier="0x%02X" % modifier, shift=shift, keys=keys,
                elapsed=round(now - started, 2),
            )
        if all(seen.values()) and counts["release_reports"]:
            stop_reason = "all sample keys observed"
            break

    counts["seen"] = seen
    counts["stop_reason"] = stop_reason
    counts["elapsed"] = round(time.monotonic() - started, 1)
    return counts


def run(seconds=PROBE_SECONDS):
    emit("probe_start", seconds=seconds, writes_files=False,
         creates_guards=False, touches_display=False)
    backend = UsbHostKeyboardBackend(emit_log, read_timeout_ms=READ_TIMEOUT_MS)
    if not survey(backend):
        emit("probe_summary", result="FAIL", reason="no device enumerated")
        return False
    try:
        identity = backend.open()
    except Exception as error:
        emit("probe_summary", result="FAIL", reason="open failed",
             detail=str(error))
        return False
    emit("probe_claimed", identity=identity)
    try:
        still_active = backend.device.is_kernel_driver_active(
            backend.interface.number
        )
    except Exception as error:
        still_active = "unknown: " + str(error)
    emit("probe_kernel_driver", interface=backend.interface.number,
         active=still_active, phase="after_claim")
    emit("probe_type_now",
         message="Type continuously: A, Shift+A, Enter, Backspace, Left arrow")
    try:
        counts = poll(backend, seconds)
    finally:
        backend.close()
    passed = (
        counts["nonzero_reports"] > 0
        and counts["release_reports"] > 0
        and counts["error_reports"] == 0
    )
    counts["result"] = "PASS" if passed else "FAIL"
    counts["identity"] = identity
    emit("probe_summary", **counts)
    return passed


def emit_log(record):
    """Adapter for the backend's structured logger."""
    print(json.dumps(record, separators=(",", ":")))


if __name__ == "__main__":
    run()
