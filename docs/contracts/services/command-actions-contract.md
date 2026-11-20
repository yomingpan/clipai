# Command Actions

## Intent and ownership

The selected Action owns task intent. Input language, code fragments, and missing
context must not select a different task. Task semantics and output instructions
belong to the official Action Language Pack resources; the canonical skeleton
owns behavior and feedback reason IDs. Existing input preparation, prompt
building, provider execution, and Workflow lifecycle are reused without a new
router or UI branch.

| Action | Task | Result |
| --- | --- | --- |
| `command_generate` | Turn short spoken or written requirements into commands | One standard, clear command first; brief intent mapping; necessary assumptions only |
| `command_copilot` | Review supplied commands or described operations | Risks, scope, uncertainty, checks, and recovery conditions; no invented original command |
| `command_coach` | Learn how to construct and recognize commands | Requirement decomposition, command construction, recall/verification tips, optional one-condition practice |

`command_copilot` retains its identity and `Ctrl+Alt+C` binding for compatibility.
Generation is the fourth Tools flagship; coaching is in Tools More/search, keeping
the existing four-flagship limit. Both new Actions have their own Human Space and
feedback reasons. `command_generate` uses `Ctrl+Alt+B` (Build), while coaching
remains available through Tools More/search without a global hotkey.

## Short commands that teach

Correctness, intended scope, and safety precede character count. Prefer a standard
command that can be retyped and inspected. Do not shorten by using custom aliases,
obscure abbreviations, dense pipelines, or removing quoting or necessary guards.
Use current-directory context, relative paths, or `HEAD` only when equivalent,
and state the execution location and data scope. Preserve supplied identifiers.

All three Actions share the `command_readable` Output Profile. In explanation
prose, emphasize commands and the parameters being taught with Markdown bold
(for example, **git status**), rather than inline backticks. Emphasize only the
relevant fragment. Complete commands remain in shell-appropriate fenced code
blocks with no bold markers added to their contents. Preserve literal command
characters, including shell backticks; this is an output instruction, not a
global text replacement or a new UI parser.

Missing context is not permission to invent a path, branch, filename, shell, or
local state. Ask only for information that materially changes the command or its
impact. A template with unresolved placeholders is not a ready-to-run command.
These Actions do not capture extra environment context, execute commands, or add
path attachment/paste UI. Voice Draft input uses the existing content path.

Coaching teaches one reusable concept, at most three key points, and one or two
relevant tips. Explain how requirements map to the command, accurate mnemonic
links, common mistakes, observable verification, and when to recall the pattern.
Practice changes one condition, is optional, and never requires destructive
execution. No learning tracker or automatic memory is introduced.

## Review examples

These are semantic review cases for each official language, not assertions that
a fake provider proves model quality. Replies should use the selected pack's
language while preserving commands and identifiers.

| Input / selected task | Expected behavior |
| --- | --- |
| Spoken: compare file names in current branch versus local `main`, no mutations / generate | `git diff --name-only main HEAD`; state repository working directory and committed endpoints, excluding uncommitted changes; concise explanation |
| Same input / coach | Map compare → `diff`, names only → `--name-only`, endpoints → `main HEAD`; recall cue and a safe optional variation such as names plus statuses |
| `git diff --name-only main HEAD` / risk review | Review read-only behavior and limits; do not switch to teaching or invent a new task |
| Reference code plus a Chinese request to change output to names only / generate | Keep generation intent despite embedded code |
| Compare “that file” in “the other branch”, with no identifiers / generate or coach | Ask the minimum specific question; do not invent identifiers or emit a runnable-looking placeholder |
| Supplied path with spaces, exact mixed-case filename and branch / any task | Preserve identifiers, apply shell-appropriate quoting, do not silently broaden scope |
| Request involving deletion, forced history changes, or a remote / generate or coach | Preserve necessary safety checks and explain the concrete consequence; never turn destructive execution into practice |

Machine checks cover complete pack compilation, topology, selected-action prompt
construction with unchanged input, feedback contracts, baseline, and architecture.
Provider output quality and learning effectiveness require the semantic review
above and actual user practice; they are not established by string assertions.
