# Display text transform contract

The popup may insert a sentinel-wrapped ASCII break space immediately before content is inserted into Tk. Windows Tk does not treat `U+200B` as a word-wrap boundary, so the adapter tags each synthetic ASCII space with a one-pixel font to make it visually negligible. This is a pure, idempotent presentation transform. Stripping the complete sentinel sequence restores the exact canonical text; selections are stripped by the UI adapter before becoming typed commands. Stored workflow content and every copy, paste, archive, speech, selection-capture, and native-control path use canonical text only.

Breaks are permitted at character boundaries unless the boundary is inside an ASCII token, a grapheme sequence, after opening punctuation, before closing punctuation, or within the spaces of a short Latin island embedded in CJK. List continuation indentation is derived from the measured, DPI-scaled width of the actual marker prefix and reapplied on scaling changes.

Rejected alternatives: enumerating CJK/script-pair rules (a combinatorial maintenance trap), splitting English words, fixed/tab-stop list indentation, and a custom text layout engine. Tk has no per-run wrapping; the display hints are the smallest reversible adapter-level intervention.
