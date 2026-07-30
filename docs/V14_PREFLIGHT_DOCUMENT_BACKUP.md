# V1.4 pre-flight document backup

Captured 2026-07-30 by the shipped read-only `tools/fruitjam_recovery_check.py`,
run on the Fruit Jam against the card the firmware had already mounted at
`/sd`. The check mounts nothing and writes nothing; this ran before any V1.4
migration touched the card.

## Recovery result

| Field | Value |
| --- | --- |
| `document_id` | `active` |
| `source` | `CHECKPOINT` |
| `recovered` | `True` |
| `revision` | `127` |
| `characters` | `125` |
| `cursor_row` | `31` |
| `cursor_column` | `12` |
| `checkpoint_records` | `3` |
| `journal_records` | `0` |
| `rejected_records` | `0` |
| `truncated_final_record` | `False` |
| `mirror_stale` | `False` |
| `lines` | `32` |

Catalogue: `0` records, `0` documents, active `None` — an empty catalogue,
which is exactly what a card written by V1.2 or V1.3 looks like before V1.4
adopts it.

## Recovered text, verbatim

```text
mnb tgus test us giubg ib 
ugh the keyboard is dece nt i guess
distinct
recignizelkjf



























sdfgdf sdfg 
```
