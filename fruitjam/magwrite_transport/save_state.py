"""The save state the writer can see, as a pure function of durability facts.

Host-safe and deliberately tiny. It holds no clock, no filesystem, and no
policy: given what has been acknowledged, what has been journaled, and what has
been checkpointed, there is exactly one honest answer, and this is where it is
computed so the status line and the diagnostics can never disagree.

The states are described from the writer's position, not the storage layer's:

``SAVED``        everything the editor has accepted is in a checkpoint
``RECOVERABLE``  it is in the journal, so a power loss recovers it
``UNSAVED``      the newest edits are in RAM only
``ERROR``        a write was attempted and refused or failed
``NO_CARD``      there is no card, so nothing is being persisted at all

``RECOVERABLE`` is a real distinction rather than a shade of ``SAVED``. It is
the state a writer spends nearly all their time in, and it is the one the whole
journal exists to provide: not yet checkpointed, but already survivable.

``NO_CARD`` is shown, never hidden. A writing tool that silently stops
persisting is worse than one that refuses to start.
"""

SAVED = "SAVED"
RECOVERABLE = "RECOVERABLE"
UNSAVED = "UNSAVED"
ERROR = "ERROR"
NO_CARD = "NO_CARD"

STATES = (SAVED, RECOVERABLE, UNSAVED, ERROR, NO_CARD)

# One character each, because the status line has four spare cells and the
# indicator must survive a 28-column panel without pushing anything off it.
#
# Every one of these is present in the MagTag's proven 3x5 glyph table -- a host
# test asserts it. The first attempt used "=" and "*", which have no glyph, so the
# renderer raised ``KeyError`` on the first frame carrying a save state. The
# indicator is drawn on the panel, so "a character" means "a character this panel
# can draw", and nothing else.
#
# Lowercase rather than uppercase so the indicator cannot be misread as part of
# the uppercase revision and row fields it sits beside.
INDICATORS = {
    SAVED: "s",
    RECOVERABLE: "r",
    UNSAVED: "u",
    ERROR: "!",
    NO_CARD: "x",
}


def evaluate(
    acknowledged_revision, journaled_revision, checkpoint_revision,
    has_storage=True, error=None,
):
    """Return the save state for these durability facts.

    ``acknowledged_revision`` is the editor's ``document_revision`` -- the latest
    revision the Fruit Jam editor accepted. The MagTag's displayed revision is
    deliberately not an input here: what is on the panel has no bearing on what
    survives a power loss, and conflating the two would let a stalled display
    make a saved document look unsaved.
    """
    if not has_storage:
        return NO_CARD
    if error:
        return ERROR
    if acknowledged_revision > journaled_revision:
        return UNSAVED
    if acknowledged_revision > checkpoint_revision:
        return RECOVERABLE
    return SAVED


def indicator(state):
    """Return the one-character status-line token for ``state``."""
    if state not in INDICATORS:
        raise ValueError("unknown save state: " + str(state))
    return INDICATORS[state]
