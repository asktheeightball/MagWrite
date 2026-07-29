"""The only module that talks to the CircuitPython USB host stack.

Importing this module is safe on the host: ``usb.core`` is imported lazily inside
:meth:`UsbHostKeyboardBackend.open`, so a plain CPython test collection never
pulls in a CircuitPython-only module, and the "USB host modules are missing" path
is itself host-testable.

Everything that can be decided without hardware lives in
``usb_hid_descriptors``. This module only performs transfers.

Observed on the real Fruit Jam (CircuitPython 10.2.1, ``adafruit_fruit_jam``):

* ``usb.core.find(find_all=True)`` enumerates attached devices;
* CircuitPython's own host keyboard driver claims the boot interface, so
  ``detach_kernel_driver`` is required before the interrupt endpoint can be read;
* descriptors come back from a standard GET_DESCRIPTOR control transfer;
* an idle interrupt read raises ``usb.core.USBTimeoutError``, which is the normal
  "no key activity" case and never an error.
"""

from magwrite_transport.usb_hid_descriptors import (
    BOOT_REPORT_SIZE, DESCRIPTOR_CONFIGURATION, HID_PROTOCOL_BOOT,
    HID_REQUEST_SET_IDLE, HID_REQUEST_SET_PROTOCOL,
    REQUEST_GET_DESCRIPTOR, REQUEST_TYPE_CLASS_INTERFACE_OUT,
    REQUEST_TYPE_STANDARD_DEVICE_IN, CONFIGURATION_HEADER_SIZE,
    EndpointInitializationError, UsbHostUnavailable, UsbKeyboardDisconnected,
    UsbKeyboardNotFound, configuration_total_length, parse_configuration,
    select_boot_keyboard,
)

READ_TIMEOUT_MS = 2
MAX_CONFIGURATION_BYTES = 512


def _load_usb_core():
    """Import ``usb.core`` lazily so host collection never touches hardware."""
    try:
        import usb.core as usb_core
    except ImportError as error:
        raise UsbHostUnavailable("usb.core is unavailable: " + str(error))
    return usb_core


class UsbHostKeyboardBackend:
    """One attached boot-protocol keyboard on the Fruit Jam USB host port."""

    def __init__(self, log, read_timeout_ms=READ_TIMEOUT_MS, load=_load_usb_core):
        self.log = log
        self.read_timeout_ms = read_timeout_ms
        self._load = load
        self._usb_core = None
        self.device = None
        self.interface = None
        self.endpoint = None
        self._buffer = bytearray(BOOT_REPORT_SIZE)

    @property
    def connected(self):
        return self.device is not None and self.endpoint is not None

    # ----------------------------------------------------------------- opening

    def _read_configuration(self, device):
        header = bytearray(CONFIGURATION_HEADER_SIZE)
        device.ctrl_transfer(
            REQUEST_TYPE_STANDARD_DEVICE_IN, REQUEST_GET_DESCRIPTOR,
            (DESCRIPTOR_CONFIGURATION << 8) | 0, 0, header,
        )
        total = configuration_total_length(header)
        if total > MAX_CONFIGURATION_BYTES:
            raise EndpointInitializationError(
                "configuration descriptor of %d bytes exceeds the %d-byte bound"
                % (total, MAX_CONFIGURATION_BYTES)
            )
        full = bytearray(total)
        device.ctrl_transfer(
            REQUEST_TYPE_STANDARD_DEVICE_IN, REQUEST_GET_DESCRIPTOR,
            (DESCRIPTOR_CONFIGURATION << 8) | 0, 0, full,
        )
        return bytes(full)

    def open(self):
        """Claim the boot keyboard and return its observed identity."""
        usb_core = self._usb_core or self._load()
        self._usb_core = usb_core
        try:
            devices = list(usb_core.find(find_all=True))
        except Exception as error:
            raise UsbKeyboardNotFound("USB enumeration failed: " + str(error))
        if not devices:
            raise UsbKeyboardNotFound("no device on the USB host port")

        failures = []
        for device in devices:
            try:
                configuration = self._read_configuration(device)
                interfaces = parse_configuration(configuration)
                interface, endpoint = select_boot_keyboard(interfaces)
            except Exception as error:
                failures.append("0x%04X/0x%04X: %s" % (
                    device.idVendor, device.idProduct, error,
                ))
                continue
            self._claim(device, interface, endpoint)
            return self._describe(device, interface, endpoint, interfaces)
        raise EndpointInitializationError(
            "no usable boot keyboard: " + "; ".join(failures)
        )

    def _claim(self, device, interface, endpoint):
        try:
            if device.is_kernel_driver_active(interface.number):
                device.detach_kernel_driver(interface.number)
            device.set_configuration()
            # Boot protocol pins the report to the fixed 8-byte layout, so no
            # report descriptor has to be parsed at runtime.
            device.ctrl_transfer(
                REQUEST_TYPE_CLASS_INTERFACE_OUT, HID_REQUEST_SET_PROTOCOL,
                HID_PROTOCOL_BOOT, interface.number, b"",
            )
            # Indefinite idle: report only on change, which keeps duplicate
            # reports rare rather than continuous.
            device.ctrl_transfer(
                REQUEST_TYPE_CLASS_INTERFACE_OUT, HID_REQUEST_SET_IDLE,
                0x0000, interface.number, b"",
            )
        except Exception as error:
            raise EndpointInitializationError(
                "could not claim interface %d: %s" % (interface.number, error)
            )
        self.device = device
        self.interface = interface
        self.endpoint = endpoint

    def _describe(self, device, interface, endpoint, interfaces):
        def text(attribute):
            try:
                return getattr(device, attribute)
            except Exception:
                return None

        return {
            "vendor_id": "%04X" % device.idVendor,
            "product_id": "%04X" % device.idProduct,
            "manufacturer": text("manufacturer"),
            "product": text("product"),
            "serial_number": text("serial_number"),
            "speed": text("speed"),
            "interface": interface.number,
            "interface_class": interface.interface_class,
            "interface_subclass": interface.subclass,
            "interface_protocol": interface.protocol,
            "endpoint": endpoint.address,
            "max_packet_size": endpoint.max_packet_size,
            "interval": endpoint.interval,
            "protocol": "boot_keyboard",
            "hid_interfaces": len(interfaces),
        }

    # ----------------------------------------------------------------- reading

    def read_report(self):
        """Return one 8-byte report, or ``None`` when nothing is pending."""
        if not self.connected:
            raise UsbKeyboardDisconnected("no claimed keyboard endpoint")
        try:
            count = self.device.read(
                self.endpoint.address, self._buffer,
                timeout=self.read_timeout_ms,
            )
        except self._usb_core.USBTimeoutError:
            return None
        except Exception as error:
            self.device = None
            self.endpoint = None
            raise UsbKeyboardDisconnected("interrupt read failed: " + str(error))
        if count < BOOT_REPORT_SIZE:
            # A short packet is not a boot report; count it as no activity
            # rather than feeding a truncated report to the translator.
            return None
        return bytes(self._buffer[:BOOT_REPORT_SIZE])

    def close(self):
        device = self.device
        self.device = None
        self.interface = None
        self.endpoint = None
        if device is None:
            return
        try:
            device.deinit()
        except Exception:
            pass
