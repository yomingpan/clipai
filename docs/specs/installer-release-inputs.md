# Installer release inputs and admission

Date: 2026-10-04. Maintainer: ClipAI release owner. Machine-readable byte pins:
[setup-inputs.json](../../packaging/windows/setup-inputs.json). Status: **pending
production distribution admission**; these are technical candidate inputs.

| Component | Fixed identity / role | Current evidence | Admission / next owner action |
| --- | --- | --- | --- |
| App | 3.7.8 wheel from r4, source `a0502d34cfa2b1ab554c480d39b8b8813d1ef201` | full first-party wheel/payload compared to Git; SHA in provenance | new real app version/tag for B; no relabeling r4 as upgrade |
| Runtime | CPython 3.12.14, PBS 20260901, baseline x86_64-pc-windows-msvc, install_only_stripped | archive SHA `7c45c9622400d578709a9b2cddbe8124cc21d382409d9f13406d706d28e31b14`; same no-site-packages profile as Preview | native/license/security admission and clean VM pending |
| Python ABI | cp312 / win_amd64; manifest requires >=3.12,<3.13 | bundle wheels and offline installed import probe | source CI Python 3.10–3.13 does not prove those runtime wheels |
| Verifier | Win32-OpenSSH 10.0.0.0p2-Preview; only ssh-keygen.exe + libcrypto.dll + LICENSE/NOTICE | archive SHA `23f50f3458c4c5d0b12217c6a5ddfde0137210a30fa870e98b29827f7b43aba5`; isolated production-key verification | upstream explicitly non-production; select/admit supported verifier before official distribution |
| Compiler | Inno Setup 6.7.3, immutable GitHub release | installer SHA `9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732`; 78 compiler files pinned; local installer signature Valid, publisher Pyrsys B.V., timestamp present | commercial eligibility/license decision and reviewed input inventory pending; no purchase made |
| Bootstrap | app package and packaging wheel from the admitted bundle, fixed entry wrapper | exact stage inventory; wheel hashes and notices shipped | no copied checkout code or newly generated key; review wrapper on protocol change |
| Launcher | app version identity at initial install, persistent private runtime/verifier | existing stager/materializer/health mechanisms | separate from app version; no runtime auto updater |
| Managed signer | Ed25519 manifest authority; existing local r4 key for this proof | local r4 signature actually verified; private key already removed | official secret/keyring/rotation authority not inventoried; never reuse local key for official release |
| Windows signer | Authenticode publisher and timestamp | no CurrentUser/My code-signing certificate observed; signtool not on PATH | lawful signer/service and publisher identity required; absence is not evidence that no external signer exists |
| Wheels / notices | one exact hashed lock + 41 wheels from r4 | inventories, wheel notice exports and per-file hashes in delivery | full dependency/license/native component mapping pending; exported notice files do not certify completeness |

Existing native inventory from 2026-10-01 reports runtime 48 native files with
44 unsigned (including venv redirectors), and the two verifier binaries Valid.
That historical evidence is [preserved](../evidence/first-install-native-inventory-20261001.json);
it is not a newly run final-signed candidate gate. Signing native inputs changes
hashes: review the final profile, rebuild pins/bundle only at its authoritative
owner, and rerun affected proofs. Do not simply sign top-level Python and omit
the venv redirectors, or mutate wheel bytes after sealing the managed manifest.

The [PBS distribution format](https://gregoryszorc.com/docs/python-build-standalone/main/distributions.html)
provides distribution/ABI/component metadata; [licensing documentation](https://gregoryszorc.com/docs/python-build-standalone/main/running.html#licensing)
requires downstream understanding of varied component licenses. Preserve the
exact archive and map its notices/ensurepip/vendor components. A stripped archive
being runnable does not itself complete this review.
The pinned [OpenSSH release](https://github.com/PowerShell/Win32-OpenSSH/releases/tag/10.0.0.0p2-Preview)
explicitly calls itself non-production ready. The [Inno official download page](https://jrsoftware.org/isdl.php)
identifies version/publisher and asks commercial users to purchase a license;
no commercial-use decision or purchase is implied here. Final Windows signature
inspection uses [Get-AuthenticodeSignature](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/get-authenticodesignature).

## Host/runner capability inventory

Read-only commands: `Get-Command python,gh,ssh-keygen,ISCC,signtool,vmrun,VBoxManage,qemu-system-x86_64`,
`Get-CimInstance Win32_OperatingSystem`, `Get-CimInstance Win32_ComputerSystem`,
`Get-Service vmms,vmcompute`, `Get-Module -ListAvailable Hyper-V`,
`Get-ChildItem Cert:/CurrentUser/My -CodeSigningCert`, `git remote -v`.

The developer environment is `.venv/Scripts/python.exe`, CPython 3.12.14 x64;
OSVersion is Windows 10.0.26200.0 (Windows 11 family). WMI queries denied access;
edition/CPU/hypervisor inventory is unavailable in that scope. `vmcompute` runs,
no Hyper-V module/confirmed clean VM/image/snapshot/license was found in the
bounded inventory. No VM setup, host setting change or image download occurred.
WindowsApps python alias is not the chosen test interpreter. Inno exists at the
workspace path recorded in the runbook; host PATH contains OpenSSH, which is not
used as the installed verifier. No gh/VM CLI/signtool was located on PATH; checked
common gh config paths were absent, and no code-signing cert was listed. This does
not establish the absence of other accounts/services: access remains unconfirmed.

Git remote is `git@github.com:yomingpan/clipai.git`; local workflow configuration
is inspected, but runner entitlement, signing secret presence and repository
permissions are pending. No credentials were read or transmitted. CI YAML and
local workflow tests are source evidence; no remote run or branch-protection
configuration was performed. A protected deployment environment may provide
an approval boundary when configured by the maintainer; [GitHub documentation](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
is the reference, not proof that this repository has one.

P2 unblocks with an existing authorized VM + licensed image + resettable snapshot
and standard-user access. Official P3/P4 unblock with admitted components, lawful
signer/publisher, exact final hashes and independent device/new-user evidence.
Keep all these gates pending/blocked until the actual capability is supplied.
