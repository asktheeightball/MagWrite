"""USB configuration-descriptor parsing and boot-keyboard selection.

Host-safe and dependency-free. ``adafruit_usb_host_descriptors`` is not
installed on the Fruit Jam and ``/lib`` is empty, so descriptors are parsed here
from the raw bytes returned by a GET_DESCRIPTOR control transfer. Keeping the
parse host-safe is the point: the exact 98-byte descriptor read off the real
receiver is a host-test fixture, so descriptor handling is proven in CPython
before any hardware runs.

The receiver used for this phase exposes *three* HID interfaces and only the
first is a keyboard, so selection is explicit and by class triple rather than
"the first HID interface wins".
"""

DESCRIPTOR_DEVICE = 0x01
DESCRIPTOR_CONFIGURATION = 0x02
DESCRIPTOR_INTERFACE = 0x04
DESCRIPTOR_ENDPOINT = 0x05
DESCRIPTOR_HID = 0x21

INTERFACE_DESCRIPTOR_SIZE = 9
ENDPOINT_DESCRIPTOR_SIZE = 7
CONFIGURATION_HEADER_SIZE = 9

CLASS_HID = 0x03
SUBCLASS_BOOT = 0x01
PROTOCOL_KEYBOARD = 0x01
PROTOCOL_MOUSE = 0x02

ENDPOINT_DIRECTION_IN = 0x80
ENDPOINT_TRANSFER_MASK = 0x03
ENDPOINT_TRANSFER_INTERRUPT = 0x03

# HID class requests issued over the control pipe.
HID_REQUEST_SET_IDLE = 0x0A
HID_REQUEST_SET_PROTOCOL = 0x0B
HID_PROTOCOL_BOOT = 0x0000
REQUEST_TYPE_CLASS_INTERFACE_OUT = 0x21
REQUEST_TYPE_STANDARD_DEVICE_IN = 0x80
REQUEST_GET_DESCRIPTOR = 0x06

BOOT_REPORT_SIZE = 8


class UsbKeyboardError(Exception):
    """Base class for every USB keyboard failure. All of them fail closed."""


class UsbHostUnavailable(UsbKeyboardError):
    """The CircuitPython USB host modules are missing."""


class UsbKeyboardNotFound(UsbKeyboardError):
    """No USB device is attached to the host port."""


class UnsupportedKeyboardInterface(UsbKeyboardError):
    """No attached device exposes a usable boot-protocol keyboard."""


class DescriptorParseError(UsbKeyboardError):
    """A descriptor was truncated, malformed, or self-inconsistent."""


class EndpointInitializationError(UsbKeyboardError):
    """The chosen interface or interrupt endpoint could not be prepared."""


class UsbKeyboardDisconnected(UsbKeyboardError):
    """The device went away mid-session."""


class Endpoint:
    __slots__ = ("address", "attributes", "max_packet_size", "interval")

    def __init__(self, address, attributes, max_packet_size, interval):
        self.address = address
        self.attributes = attributes
        self.max_packet_size = max_packet_size
        self.interval = interval

    @property
    def is_in(self):
        return bool(self.address & ENDPOINT_DIRECTION_IN)

    @property
    def is_interrupt(self):
        return (
            self.attributes & ENDPOINT_TRANSFER_MASK
        ) == ENDPOINT_TRANSFER_INTERRUPT

    def describe(self):
        return {
            "address": self.address,
            "attributes": self.attributes,
            "max_packet_size": self.max_packet_size,
            "interval": self.interval,
        }


class Interface:
    __slots__ = (
        "number", "alternate", "interface_class", "subclass", "protocol",
        "endpoints",
    )

    def __init__(self, number, alternate, interface_class, subclass, protocol):
        self.number = number
        self.alternate = alternate
        self.interface_class = interface_class
        self.subclass = subclass
        self.protocol = protocol
        self.endpoints = []

    @property
    def is_boot_keyboard(self):
        return (
            self.interface_class == CLASS_HID
            and self.subclass == SUBCLASS_BOOT
            and self.protocol == PROTOCOL_KEYBOARD
        )

    def interrupt_in_endpoint(self):
        for endpoint in self.endpoints:
            if endpoint.is_in and endpoint.is_interrupt:
                return endpoint
        return None

    def describe(self):
        return {
            "interface": self.number,
            "alternate": self.alternate,
            "class": self.interface_class,
            "subclass": self.subclass,
            "protocol": self.protocol,
            "endpoints": [endpoint.describe() for endpoint in self.endpoints],
        }


def configuration_total_length(header):
    """Read ``wTotalLength`` from a configuration descriptor header."""
    if header is None or len(header) < CONFIGURATION_HEADER_SIZE:
        raise DescriptorParseError("configuration header is too short")
    if header[1] != DESCRIPTOR_CONFIGURATION:
        raise DescriptorParseError("not a configuration descriptor")
    total = header[2] | (header[3] << 8)
    if total < CONFIGURATION_HEADER_SIZE:
        raise DescriptorParseError("impossible configuration total length")
    return total


def parse_configuration(data):
    """Walk a full configuration descriptor and return its interfaces."""
    if data is None or len(data) < CONFIGURATION_HEADER_SIZE:
        raise DescriptorParseError("configuration descriptor is too short")
    if data[1] != DESCRIPTOR_CONFIGURATION:
        raise DescriptorParseError("not a configuration descriptor")
    interfaces = []
    current = None
    at = 0
    while at < len(data):
        length = data[at]
        if length == 0:
            raise DescriptorParseError("zero-length descriptor")
        if at + length > len(data):
            raise DescriptorParseError("descriptor runs past the buffer")
        kind = data[at + 1]
        if kind == DESCRIPTOR_INTERFACE:
            if length < INTERFACE_DESCRIPTOR_SIZE:
                raise DescriptorParseError("short interface descriptor")
            current = Interface(
                data[at + 2], data[at + 3], data[at + 5], data[at + 6],
                data[at + 7],
            )
            interfaces.append(current)
        elif kind == DESCRIPTOR_ENDPOINT:
            if length < ENDPOINT_DESCRIPTOR_SIZE:
                raise DescriptorParseError("short endpoint descriptor")
            if current is None:
                raise DescriptorParseError("endpoint before any interface")
            current.endpoints.append(Endpoint(
                data[at + 2], data[at + 3],
                data[at + 4] | (data[at + 5] << 8), data[at + 6],
            ))
        at += length
    if not interfaces:
        raise DescriptorParseError("configuration declares no interface")
    return tuple(interfaces)


def select_boot_keyboard(interfaces):
    """Return the ``(interface, endpoint)`` pair to read boot reports from.

    Selection is by the HID class triple, so a combo receiver's mouse and
    consumer-control interfaces are never mistaken for the keyboard.
    """
    for interface in interfaces:
        if not interface.is_boot_keyboard:
            continue
        endpoint = interface.interrupt_in_endpoint()
        if endpoint is None:
            raise EndpointInitializationError(
                "boot keyboard interface %d has no interrupt IN endpoint"
                % interface.number
            )
        if endpoint.max_packet_size < BOOT_REPORT_SIZE:
            raise EndpointInitializationError(
                "endpoint 0x%02X cannot carry an %d-byte boot report"
                % (endpoint.address, BOOT_REPORT_SIZE)
            )
        return interface, endpoint
    raise UnsupportedKeyboardInterface(
        "no HID boot-protocol keyboard interface among %d interface(s)"
        % len(interfaces)
    )
