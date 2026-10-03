# First-install experiments and local Preview build

These tools produce bounded developer-host evidence. An unsigned Preview is
not an official release; public signing/admission and clean-VM gates remain in
[the plan](../../docs/specs/first-install-installer-plan.md).

`build_preview.py` consumes hash-pinned runtime/verifier archives, a local
wheelhouse, a caller-supplied Python build backend and Inno Setup 6.7.3 ISCC.
It builds the changed ClipAI wheel offline, seals an exact hashed lock/bundle
with a fresh local manifest key, deletes the private key and compiles a Setup.
Each build uses a fresh directory and emits build-evidence.json. No official
keyring, publisher credentials or GitHub publishing is involved.

`accept_preview.py --setup <exe> --output <new-evidence-directory>` exercises the
actual Setup against its default isolated per-user Preview root. It rejects an
existing Preview installation/registration, preserves existing shared data,
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
