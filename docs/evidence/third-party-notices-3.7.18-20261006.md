# 3.7.18 component notice review

Date: 2026-10-06. Scope: pinned runtime and sealed wheelhouse, unsigned Windows
packaging. The fixed input profile is approved after the compiled proof recorded
below. Final official assets and device acceptance are separate gates.

The f637065 validation bundle SHA-256 is
`02da0d2979a6f536a1ac31bfdae08efece9e99d442db476899711485235c74f9`.
Its 42 wheels were inventoried against the manifest; original wheel bytes remain
unchanged. Third-party wheels have upstream notices except proxy_tools, whose
source license is supplied separately. This review assigns no ClipAI license.

Native inspection covered 230 EXE/DLL/PYD files without executing them:
125 NotSigned and 105 Valid, with no damaged/untrusted/unknown signatures.
[Per-file hashes and subjects](native-components-3.7.18-20261006.json) are retained.
Source admission and loading evidence remain distinct from Windows publisher
trust; unsigned upstream bytes are preserved under the explicit unsigned policy.

| Component | Review and retained material |
| --- | --- |
| CPython/PBS | Matching 3.12.14/20260901 full build metadata and PSF/CNRI, bzip2, expat, libffi, liblzma, libuuid, mpdecimal, OpenSSL 3, SQLite, Tcl/Tix and zlib texts. gdbm/readline GPL extensions are absent from this Windows profile. |
| cryptography/cffi/pycparser | Sealed wheels, actual bootstrap native imports and Ed25519 verification passed Windows CI. Upstream notices retained. No runtime OpenSSH Preview. |
| proxy_tools 0.1.0 | Metadata says MIT; source headers and immutable upstream license are BSD. Preserve actual BSD copyright/conditions. |
| Pygame-CE 2.5.3 | LGPL and vendor notices supplemented from exact PyPI source; corresponding source archive is a required release asset. |
| SDL2_ttf 2.24.0 | DLL matches official x64 SDK. SDL notice, FreeType license/attribution and HarfBuzz COPYING from the release's pinned submodule are retained. |
| SDL2_mixer 2.8.0 | Mixer/xmp/wavpack/opus/opusfile/ogg DLL hashes match official x64 SDK. Preserve matching SDK notices. libgme is not shipped; xmp uses MIT and WavPack BSD. |
| Other wheels | Retain upstream notices, including Pillow/miniaudio native materials and Certifi MPL. LGPL edge-tts/pynput/pystray source remains in separate pure-Python modules. |
| Inno 6.7.3 | Pinned license permits commercial use/redistribution subject to notice/origin conditions. No compiler, certificate or signing-service payment made. |

There are **46** pinned supplemental files under
`packaging/windows/third-party-notices/`. Input sizes, SHA-256 and source locations
are recorded in `setup-inputs.json`. Altered notices fail before compilation.
They are installed in the setup engine and exported with release notices.
The exporter recognizes LGPL filenames, `license.terms` and license folders;
`.gitattributes` preserves original notice bytes across Windows checkouts.

Pygame source: 6,987,675 bytes,
`dc04f0bf1a270a84eb371556298a9902b9c4ab08137c9dd10ef03fa4e7fcbfed`.
HTTPS download enforces exact size/hash and safe filename; archives do not execute.
Missing or substituted corresponding source assets fail release verification.
Publish these source bytes alongside the binary release.

SDK evidence: SDL2_ttf ZIP 11,640,089 bytes,
`2dea8ea01e04756ead27e196a681034ed71342562a75b512ea279fcdfde83307`;
SDL2_mixer ZIP 1,991,107 bytes,
`47a5713937f8d8b903a9c5555fef3ec73a793ef95abdd078773fc11fcb00ec8a`.
SDKs are provenance evidence, not new installed dependencies.

Verification: targeted source/notice/workflow tests passed (44 tests, 14.77s).
The final unit/architecture suite passed **2,022 tests**, 64 deselected, 106.66s.
An initial targeted invocation used the host Python without PyYAML; rerunning
with the project's explicit venv passed. Fresh Windows packaging is still pending.

The bdeef09 Windows source matrix passed. Candidate run 37472629909 passed the
2,022-test suite and complete managed transaction, then failed before compilation:
PowerShell unwrapped a one-element conditional array and native splatting split
the mode string into characters. Mode is now constructed as an array before
conditional append. A real PowerShell-to-Python argv regression covers branch
and tag behavior; all four workflow tests passed. No failed run is admitted as
compiled-payload proof; input admission was still pending at that failed run.

## Fixed input admission

The corrected local packaging adapter actually compiled the f637065 sealed bundle
with all 46 supplemental notices. Packaged offline imports, bootstrap signature
verification, full Setup extraction and asset/source identity checks passed.
Every pinned notice was found with its exact hash in both the compiled stage
inventory and exported notice directory. Actual native inspection returned
NotSigned with null publisher/timestamp.

Setup SHA-256:
`b47cf92c08ceef8b97b77f58c06ccbc78ae4bb5fe8593252022b59c91ee141c9`.
Bundle SHA-256:
`02da0d2979a6f536a1ac31bfdae08efece9e99d442db476899711485235c74f9`.
Evidence: `artifacts/official-release-3.7.18/notice-payload-proof/output/`.
The receipt `notice-admission-proof.json` records 46 notices and explicitly sets
formal_candidate/device_evidence false. These bytes are technical input evidence,
not a promoted official Setup; the app source remains the earlier f637065 snapshot.

On this reviewed source/license/native/compiled-notice basis, the pinned bootstrap
input profile is approved under the explicit unsigned policy. Approval does not
waive production-key/tag binding, latest source CI, the exact final Setup/bundle
acceptance or any remaining independent device/user gate.

The d6ce838 Python 3.12 matrix had one ordering-test failure caused by a real 15 ms
scheduler delay exceeding its 10 ms modifier deadline. A test-local controlled
clock now exercises release ordering without changing product timeout policy.
The 28 selection/workflow regressions passed, 2.32s. Latest corrected Windows
matrix and compiled installer recovery cycle still need terminal success.

Primary sources:
[PBS licensing](https://gregoryszorc.com/docs/python-build-standalone/main/running.html#licensing),
[Pygame-CE](https://pypi.org/project/pygame-ce/2.5.3/),
[SDL2_ttf](https://github.com/libsdl-org/SDL_ttf/releases/tag/release-2.24.0),
[SDL2_mixer](https://github.com/libsdl-org/SDL_mixer/releases/tag/release-2.8.0),
[proxy_tools](https://github.com/jtushman/proxy_tools/blob/ccd35a569b95bec271a59890780c7821756c548a/LICENSE.txt),
[HarfBuzz](https://github.com/libsdl-org/harfbuzz/blob/e18e66409d0136cc8f8b05aac791f84314520676/COPYING),
[Inno](https://jrsoftware.org/files/is/license.txt).
