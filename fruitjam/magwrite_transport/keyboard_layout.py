"""Per-device HID usage compatibility, kept strictly out of the standard keymap.

Host-safe. ``hid_keymap`` implements HID Usage Page 0x07 as specified and is not
allowed to drift for the convenience of one keyboard. This module is where a
*specific device* that does not follow the specification is accommodated, by
name, with recorded evidence, and without touching anyone else's behaviour.

The measured problem
--------------------

The EPOMAKER TH40 (``36B0:304E``), the 40% board used for the physical phase,
emits usage ``0x2E`` from the key the writer presses for an apostrophe. Usage
``0x2E`` is *Keyboard = and +* in the specification; the apostrophe is ``0x34``.

The behaviour was diagnosed before anything was changed, from the guarded run's
own records in ``docs/FRUITJAM_USB_KEYBOARD_SERIAL.jsonl``:

    {"event":"hid_report_received","modifier":0,"keys":[46,0,0,0,0,0], ...}
    {"event":"usb_keyboard_unsupported_usage","usage":46,"unsupported_usages":1}

``46`` is ``0x2E`` and the modifier byte is ``0``. That single fact settles what
this is and what it is not:

* it is **not** a Shift question — no Shift bit is set;
* it is **not** an Fn or AltGr layer question — no modifier bit of any kind is
  set, whereas the TH40's Fn layer demonstrably *does* set modifier bits
  (``FRUITJAM_USB_KEYBOARD_PROBE.jsonl`` shows its Fn combinations arriving as
  ``0x40`` right-alt and ``0x10`` right-ctrl alongside usage ``0x65``);
* it is **not** a translation fault — ``0x2E`` was translated correctly, to
  ``=``/``+``, which has no glyph in the proven table, so it was counted as
  unsupported and ignored exactly as designed.

The keyboard is simply sending the wrong usage for that physical key. So the
fix belongs to the device, not to the standard.

The rule
--------

A layout is a named, bounded usage remap selected from the USB descriptor the
backend already reports. ``STANDARD`` remaps nothing and is what every
unrecognised keyboard gets, so the default path is unchanged and fail-safe. A
device only ever gets a remap if its vendor and product identifiers match a
recorded entry.

Remapping is applied at translation only. The held-key set, press and release
tracking, and repeat ownership all keep the *raw* usage the keyboard sent, so a
remap can never desynchronise a release from its press.

What this deliberately does not do
----------------------------------

Home, End and Delete were never reachable on the TH40 during the probe — every
attempt at its Fn layer switched the keyboard out of USB mode entirely, so no
report was ever captured. There is therefore no evidence of what usages, if
any, that board sends for them, and no entry is invented here. They stay
unresolved on this keyboard and are handled by the standard mapping, which is
correct for every keyboard that can actually reach them.
"""


class DeviceLayout:
    """A named usage remap for one identified keyboard."""

    __slots__ = ("name", "usage_remap", "vendor_id", "product_id", "note")

    def __init__(self, name, usage_remap=None, vendor_id=None, product_id=None,
                 note=""):
        self.name = name
        self.usage_remap = dict(usage_remap or {})
        self.vendor_id = normalize_id(vendor_id)
        self.product_id = normalize_id(product_id)
        self.note = note

    @property
    def remaps(self):
        return len(self.usage_remap)

    def usage(self, usage):
        """Return the usage to translate, which is ``usage`` unless remapped."""
        return self.usage_remap.get(usage, usage)

    def describe(self):
        return {
            "layout": self.name,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "usage_remaps": {
                "0x%02X" % source: "0x%02X" % target
                for source, target in sorted(self.usage_remap.items())
            },
        }


def normalize_id(value):
    """Accept ``"36B0"``, ``"0x36b0"`` or ``0x36B0`` and return ``"36B0"``."""
    if value is None:
        return None
    if isinstance(value, int):
        return "%04X" % value
    text = str(value).strip().upper()
    if text.startswith("0X"):
        text = text[2:]
    return text.zfill(4)


USAGE_EQUALS_AND_PLUS = 0x2E
USAGE_APOSTROPHE_AND_QUOTE = 0x34

STANDARD = DeviceLayout("STANDARD", note="HID Usage Page 0x07 as specified")

EPOMAKER_TH40 = DeviceLayout(
    "EPOMAKER_TH40",
    {USAGE_EQUALS_AND_PLUS: USAGE_APOSTROPHE_AND_QUOTE},
    vendor_id="36B0",
    product_id="304E",
    note=(
        "Sends 0x2E with no modifier from its apostrophe key; 0x34 is never "
        "emitted. Diagnosed from FRUITJAM_USB_KEYBOARD_SERIAL.jsonl."
    ),
)

LAYOUTS = (STANDARD, EPOMAKER_TH40)
LAYOUTS_BY_NAME = {layout.name: layout for layout in LAYOUTS}

AUTO = "AUTO"


def descriptor_ids(descriptor):
    """Return ``(vendor_id, product_id)`` from a backend descriptor, or nulls."""
    if not isinstance(descriptor, dict):
        return None, None
    return (
        normalize_id(descriptor.get("vendor_id")),
        normalize_id(descriptor.get("product_id")),
    )


def layout_for(descriptor):
    """Select a layout from a USB descriptor. Unknown devices get ``STANDARD``."""
    vendor_id, product_id = descriptor_ids(descriptor)
    if vendor_id is None or product_id is None:
        return STANDARD
    for layout in LAYOUTS:
        if layout.vendor_id == vendor_id and layout.product_id == product_id:
            return layout
    return STANDARD


def resolve(selection, descriptor):
    """Resolve a configured selection, which is ``AUTO`` or an exact name."""
    if selection is None or selection == AUTO:
        return layout_for(descriptor)
    try:
        return LAYOUTS_BY_NAME[selection]
    except KeyError:
        raise ValueError("unknown keyboard layout: %s" % selection)
