# ADR-0003: Single clipboard transaction ownership

## Status

Accepted.

## Context

Selection capture and paste previously owned separate locks and restore paths. They could interleave temporary content, restore an unrelated snapshot, and forced a normal text transaction to encode clipboard images as optimized PNG data.

## Decision

One container-scoped `ClipboardTransactionCoordinator` owns every temporary clipboard mutation used by selection capture, speech selection, and paste. It serializes operations, records sequence ownership, polls cancellation during selection capture, and restores only when the clipboard sequence still belongs to that operation.

Selection timing and fallback policy live in services. The platform adapter exposes only modifier state and Ctrl+C primitives. `ClipboardTransactionStore` is generic over an opaque snapshot type, so Windows stores lossless native clipboard-format bytes without leaking format knowledge into services. Provider-facing `read_image()` performs image decoding and PNG encoding only when an image input is requested.

## Consequences

- Selection and paste cannot overlap temporary ownership.
- External clipboard changes are never overwritten by a late restore.
- Text-only transactions avoid image conversion cost.
- Snapshot representation can evolve inside the platform adapter without changing service contracts.
- On Windows, native snapshots serialize only clipboard formats documented as
  `HGLOBAL`-backed. Opaque bitmap, palette, metafile, private, registered, and
  GDI-object handles are never passed to `GlobalSize` or `GlobalLock`; image
  content remains restorable through the standard `CF_DIB` and `CF_DIBV5`
  formats.
