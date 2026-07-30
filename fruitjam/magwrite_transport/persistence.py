"""Autosave and checkpoint policy: *when* the document is made durable.

Host-safe, and the single home for every persistence timing constant, exactly as
``pacing`` is for display timing and ``keyboard_repeat`` is for keyboard timing.
Nothing downstream may hard-code an autosave interval, and ``config`` may only
mirror the values below; a host test asserts the two agree.

The separation this module depends on
------------------------------------

``DocumentStore`` knows how to write durably. This knows when. The split matters
because the two fail differently and are tested differently: the store is tested
against simulated power loss, and the policy is tested against a clock.

What "acknowledged" means here
------------------------------

The acknowledged revision is ``editor.document_revision`` -- the latest revision
the **Fruit Jam editor** accepted. It is not the MagTag's displayed revision.

This is a deliberate decision and the reason durability is decoupled from the
panel. A display acknowledgement tells you a refresh finished; it says nothing
about whether the words survive a power cut, and it can be delayed by up to a
full refresh or blocked indefinitely by a display fault. If persistence waited
for it, a stalled panel would silently stop saving, which is the exact failure
this phase exists to make impossible. Display acknowledgements govern pacing;
editor acceptance governs durability.

The policy
----------

Two tiers, because they cost different amounts.

**Journalling** is one bounded append. It is cheap, so it happens often: after a
short pause, after enough revisions, or after a bounded time, whichever comes
first. The pause trigger is the important one -- a writer who stops typing gets
their work journaled almost immediately, which is when they are most likely to
walk away from the desk.

**Checkpointing** promotes the newest snapshot, discards the journal, and
rewrites the plain-text mirror. It is several writes, so it prefers to happen in
a gap: when the journal has grown past its soft bound *and* the writer has
paused, or on a long interval, or -- regardless of what the writer is doing --
once the journal reaches its hard bound. The hard bound is what stops an
uninterrupted burst from growing the journal without limit.

At most one storage operation runs per service call. A checkpoint is not
followed by anything else in the same iteration, so the loop's other stages are
never starved by storage work.
"""

from magwrite_transport import save_state
from magwrite_transport.journal import Snapshot

# --------------------------------------------------------------- autosave tier

# A pause of this length means the writer stopped, and stopping is exactly when
# unsaved work is most exposed. Comfortably longer than the gap inside a typed
# word at any realistic speed, so it does not fire mid-burst.
AUTOSAVE_IDLE_SECONDS = 1.0
# The longest an accepted edit may exist in RAM only while typing continues, and
# therefore the exposure a writer who never pauses is asked to accept. At roughly
# 60 words per minute -- five characters a second -- two seconds is about ten
# characters. Five seconds was the first value here and it is too generous: half
# a sentence is a real amount of work to lose to a power cut, and the write that
# would have prevented it is a single bounded append.
AUTOSAVE_MAX_AGE_SECONDS = 2.0
# ``document_revision`` advances once per text change, so this is roughly a
# number of characters. Set just above what the age bound above admits at a
# normal typing speed, so the two agree on the same exposure rather than one
# quietly making the other unreachable.
AUTOSAVE_REVISIONS = 12

# ------------------------------------------------------------ checkpoint tier

# Soft bound: enough journal records to be worth compacting, taken at the next
# pause rather than immediately.
CHECKPOINT_RECORDS = 24
# Hard bound: checkpoint even mid-burst. Without this an unbroken burst grows the
# journal until the card fills.
CHECKPOINT_MAX_RECORDS = 48
# A quiet writer still gets their mirror refreshed on this interval.
CHECKPOINT_MAX_AGE_SECONDS = 120.0
# A checkpoint is several writes, so it waits for a slightly longer gap than a
# journal append does.
CHECKPOINT_IDLE_SECONDS = 3.0

ACTION_NONE = "NONE"
ACTION_JOURNALED = "JOURNALED"
ACTION_CHECKPOINTED = "CHECKPOINTED"
ACTION_FAILED = "FAILED"


class PersistenceController:
    """Loop stage 7: run autosave and checkpoint work when it is due.

    Constructed with ``store=None`` when there is no usable card. That is a
    supported mode, not an error path to be avoided: the editor keeps working,
    every decision below becomes a no-op, and the save state reports ``NO_CARD``
    so the writer is told rather than misled.
    """

    def __init__(
        self, store, now, log=None,
        autosave_idle_seconds=AUTOSAVE_IDLE_SECONDS,
        autosave_max_age_seconds=AUTOSAVE_MAX_AGE_SECONDS,
        autosave_revisions=AUTOSAVE_REVISIONS,
        checkpoint_records=CHECKPOINT_RECORDS,
        checkpoint_max_records=CHECKPOINT_MAX_RECORDS,
        checkpoint_max_age_seconds=CHECKPOINT_MAX_AGE_SECONDS,
        checkpoint_idle_seconds=CHECKPOINT_IDLE_SECONDS,
        storage_detail=None,
    ):
        if autosave_idle_seconds <= 0 or autosave_max_age_seconds <= 0:
            raise ValueError("autosave intervals must be positive")
        if autosave_revisions < 1 or checkpoint_records < 1:
            raise ValueError("autosave and checkpoint bounds must be positive")
        if checkpoint_max_records < checkpoint_records:
            raise ValueError("the hard record bound must not be below the soft one")
        self.store = store
        self.log = log
        self.autosave_idle_seconds = autosave_idle_seconds
        self.autosave_max_age_seconds = autosave_max_age_seconds
        self.autosave_revisions = autosave_revisions
        self.checkpoint_records = checkpoint_records
        self.checkpoint_max_records = checkpoint_max_records
        self.checkpoint_max_age_seconds = checkpoint_max_age_seconds
        self.checkpoint_idle_seconds = checkpoint_idle_seconds
        # Reported by the storage layer so a degraded session can say *why* it is
        # degraded rather than only that it is.
        self.storage_detail = storage_detail

        self.last_input_at = now
        self.last_journal_at = now
        self.last_checkpoint_at = now
        self.acknowledged_revision = 0
        self.journals = 0
        self.checkpoints = 0
        self.failures = 0
        self.manual_saves = 0
        self.last_action = ACTION_NONE
        self.recovery = None
        # V1.4. Set by ``storage_bringup`` when a catalogue could be brought up,
        # and carried here rather than constructed here for the same reason
        # ``recovery`` is: this class owns *when to write*, and knows nothing
        # about which document it is writing. The entry point reads them across
        # into the session.
        self.index = None
        self.library = None
        self.document_entry = None

    # ---------------------------------------------------------------- queries

    @property
    def has_storage(self):
        return self.store is not None

    @property
    def journaled_revision(self):
        return 0 if self.store is None else self.store.journaled_revision

    @property
    def checkpoint_revision(self):
        return 0 if self.store is None else self.store.checkpoint_revision

    @property
    def error(self):
        return None if self.store is None else self.store.last_error

    @property
    def state(self):
        return save_state.evaluate(
            self.acknowledged_revision, self.journaled_revision,
            self.checkpoint_revision, has_storage=self.has_storage,
            error=self.error,
        )

    @property
    def indicator(self):
        return save_state.indicator(self.state)

    def quiet(self, now, seconds):
        return now - self.last_input_at >= seconds

    # ---------------------------------------------------------------- signals

    def note_input(self, now):
        """The writer typed. Called from the same place pacing is told."""
        self.last_input_at = now

    def adopt(self, editor):
        """Take ``editor``'s current revision as already durable.

        Used immediately after a recovered document is loaded, so a restored
        session does not immediately rewrite the state it was just restored from.
        """
        self.acknowledged_revision = editor.document_revision

    # ------------------------------------------------------------------ policy

    def _snapshot(self, editor):
        return Snapshot(
            editor.document_revision, editor.row, editor.column, editor.text
        )

    def _journal_due(self, now, revision):
        if revision <= self.journaled_revision:
            return False
        if revision - self.journaled_revision >= self.autosave_revisions:
            return True
        if now - self.last_journal_at >= self.autosave_max_age_seconds:
            return True
        return self.quiet(now, self.autosave_idle_seconds)

    def _checkpoint_due(self, now, revision):
        if self.store is None:
            return False
        records = self.store.journal_records
        if not records and revision <= self.checkpoint_revision:
            return False
        if records >= self.checkpoint_max_records:
            return True
        if now - self.last_checkpoint_at >= self.checkpoint_max_age_seconds:
            return True
        if records >= self.checkpoint_records:
            return self.quiet(now, self.checkpoint_idle_seconds)
        return False

    def service(self, now, editor):
        """Run at most one storage operation. Returns the action taken."""
        revision = editor.document_revision
        self.acknowledged_revision = revision
        if self.store is None:
            self.last_action = ACTION_NONE
            return ACTION_NONE

        # A checkpoint also makes the newest snapshot durable, so when both are
        # due there is no reason to append first and rewrite a moment later.
        if self._checkpoint_due(now, revision):
            return self._checkpoint(now, editor)
        if self._journal_due(now, revision):
            return self._journal(now, editor)
        self.last_action = ACTION_NONE
        return ACTION_NONE

    def save_now(self, now, editor):
        """Manual save: checkpoint immediately, whatever the thresholds say."""
        self.acknowledged_revision = editor.document_revision
        self.manual_saves += 1
        if self.store is None:
            self._log({"event": "manual_save_refused", "reason": "no storage",
                       "detail": self.storage_detail})
            self.last_action = ACTION_NONE
            return ACTION_NONE
        return self._checkpoint(now, editor, manual=True)

    # ------------------------------------------------------------------ writes

    def _journal(self, now, editor):
        snapshot = self._snapshot(editor)
        if not self.store.journal(snapshot):
            return self._failed("journal", snapshot)
        self.last_journal_at = now
        self.journals += 1
        self.last_action = ACTION_JOURNALED
        self._log({
            "event": "document_journaled", "revision": snapshot.revision,
            "characters": len(snapshot.text),
            "journal_records": self.store.journal_records,
            "save_state": self.state,
        })
        return ACTION_JOURNALED

    def _checkpoint(self, now, editor, manual=False):
        snapshot = self._snapshot(editor)
        if not self.store.checkpoint(snapshot):
            return self._failed("checkpoint", snapshot)
        self.last_checkpoint_at = now
        self.last_journal_at = now
        self.checkpoints += 1
        self.last_action = ACTION_CHECKPOINTED
        self._log({
            "event": "document_checkpointed", "revision": snapshot.revision,
            "characters": len(snapshot.text), "manual": manual,
            "save_state": self.state,
        })
        return ACTION_CHECKPOINTED

    def _failed(self, operation, snapshot):
        """A refused write is reported and counted; it never stops the editor."""
        self.failures += 1
        self.last_action = ACTION_FAILED
        self._log({
            "event": "document_save_failed", "operation": operation,
            "revision": snapshot.revision, "detail": self.error,
            "save_state": self.state,
        })
        return ACTION_FAILED

    def _log(self, record):
        if self.log is not None:
            self.log(record)

    # ----------------------------------------------------------------- summary

    def summary(self):
        record = {
            "storage_present": self.has_storage,
            "storage_detail": self.storage_detail,
            "acknowledged_revision": self.acknowledged_revision,
            "journaled_revision": self.journaled_revision,
            "checkpoint_revision": self.checkpoint_revision,
            "autosaves": self.journals,
            "checkpoints": self.checkpoints,
            "manual_saves": self.manual_saves,
            "save_failures": self.failures,
            "save_state": self.state,
            "save_indicator": self.indicator,
        }
        if self.recovery is not None:
            record["recovery"] = self.recovery.summary()
        if self.store is not None:
            record.update(self.store.summary())
        return record
