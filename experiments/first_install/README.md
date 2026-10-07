# First-install experiments and candidate acceptance

These tools produce bounded developer-host evidence. An unsigned Preview is
not an official release; public signing/admission and clean-VM gates remain in
[the plan](../../docs/specs/first-install-installer-plan.md).

The old `build_preview.py` was retired on 2026-10-07. It duplicated packaging
and copied bootstrap code from the checkout while shipping the superseded
OpenSSH runtime verifier. Historical Preview evidence and its wizard include
remain available; they do not define the current packaging path.

Build new isolated candidates using
`python -m scripts.build_setup_release --technical-candidate` with the same fixed bundle/catalog/keyring and reviewed
Setup inputs used by release CI. This consumes the existing signed bundle,
extracts bootstrap code from its admitted wheels and does not rebuild or sign
the application. See [the release checklist](../../docs/RELEASE_CHECKLIST.md)
for the build order and proofs. `prepare_acceptance_pair.py` uses that same
packaging path for source-bound A/B candidates sharing a disposable authority.
Neither candidate mode grants publication authority.

`accept_preview.py --setup <exe> --output <new-evidence-directory>` exercises the
actual Setup against its default isolated per-user Preview root. Use
`--product "ClipAI Candidate" --version <version>` for current technical
candidates. It rejects an existing installation/registration, preserves existing shared data,
uses empty PATH, checks identity and full dependencies, rejects duplicate
installation and removal with its own private Python child, breaks the app venv
and proves same-Setup retained-data uninstall/reinstall. It removes the test
installation at the end and deletes only its exact synthetic shared sentinel.
It requires authorization for native per-user registry/Start Menu mutations.

The Setup switch `/REMOVE=1` selects the same removal intent for this test;
it is not a separate enterprise deployment or silent-install support promise.
Native Setup returns custom code 100 for engine failure, because an exception
from Inno's ssPostInstall event alone does not make Setup return failure.

`desktop_startup_probe.py` runs only with the installed application's Python.
It uses the real desktop instance gate and skips when the user's ClipAI is
running. Otherwise it builds the real desktop runtime and explicitly enqueues
ShutdownApplication after readiness. It does not request a provider result,
capture selection or change clipboard. Real first-use remains manual acceptance.

Older runtime/signature/inventory probes in this directory remain A-stage
evidence. Their synthetic-bundle success is not full application acceptance.

Manual instructions: [Preview acceptance](../../docs/specs/first-install-preview-acceptance.md).

`managed_desktop_probe.py` additionally exercises the full managed launch and
identity-bound health channel using an admitted installed payload. Its test
entry measures console presence at real desktop readiness and schedules an
explicit typed shutdown. Run only after the user exits ClipAI. Use an isolated
workspace root when the packaged developer host virtualizes AppData; never
weaken containment checks to make a probe pass.

`setup_result_probe.py` compiles the actual wizard script with a harmless fixture
engine (phase + exit only), runs failure/success Remove in silent mode, and reads
the final captions from DeinitializeSetup. It proves stock Inno completion text
cannot overwrite removal results. It never installs or removes an application.
