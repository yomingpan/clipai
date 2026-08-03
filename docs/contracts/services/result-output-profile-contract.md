# Result Output Profile Contract

## Status and ownership

`OutputProfileCatalog` is the owner of reusable output-format instructions,
presentation mode, and structural markers. `config/output_profiles.yaml` is the
authoritative configuration source for those values.

The ownership path is:

```text
config/output_profiles.yaml
  -> config loader validation
  -> OutputProfileCatalog
     -> PromptBuilder instruction
     -> ResultProcessor presentation and marker validation
```

Actions and press variants reference a profile ID. They own task semantics,
domain vocabulary, safety constraints, and genuinely Action-specific content;
they do not own a second reusable presentation schema.

## Protected behavior

- Config loading rejects unknown profile IDs for Actions and press variants.
- `PromptBuilder` appends the resolved profile instruction once to the system
  message. Providers do not read config or interpret profiles.
- `ResultProcessor` uses the same resolved profile to validate required markers,
  choose the presentation mode, and build a typed immutable presentation model.
- Missing markers or unsupported presentation structure produce diagnostics and
  safe readable fallback; they do not rewrite canonical content.
- UI renders the typed presentation document. Copy, paste, archive, and speech
  consume canonical text or an explicit semantic selection and never infer the
  LLM schema from styled widgets.

## Current migration debt

Some existing entries in `config/actions.yaml`, notably English-learning,
English-improvement, and SCORE-oriented Actions, repeat parts of their selected
profile's reusable formatting instructions. This is verified configuration
drift, not an accepted second owner.

Classification: **Yellow**. Keep the current bounded behavior until prompt
regression coverage exists, but do not add another duplicate format rule. Three
similar additions would multiply prompt edits, profile edits, validation cases,
and review ambiguity across every affected Action.

## Enforcement and migration

New or changed reusable formatting belongs in `config/output_profiles.yaml`.
Action prompts may describe what information to produce, but shared section
names, ordering, markers, presentation mode, and generic formatting constraints
belong to the profile.

Migration is incremental and reversible:

1. Add golden prompt-composition and representative result-validation tests for
   one duplicated profile/Action pair.
2. Move only the duplicated reusable wording into the profile; retain
   Action-specific semantics in the Action.
3. Verify base Action and press-variant resolution use the same profile and that
   the profile instruction occurs exactly once.
4. Repeat for the next pair. Do not leave old and new ownership paths active
   after each migrated pair.

Completion criteria:

- no Action repeats reusable profile markers or presentation instructions;
- every Action and variant references a known profile;
- prompt composition injects each profile once;
- result processing and UI fallback preserve canonical text;
- an automated config/architecture check detects future reusable duplication.

Review this boundary if an Action needs a truly unique structure that cannot be
expressed as task semantics plus an existing profile. Prefer a new reusable
profile when two Actions need the same structure; do not branch on Action ID in
runtime or UI.
