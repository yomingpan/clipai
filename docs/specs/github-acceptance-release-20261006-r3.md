# GitHub health timeout acceptance release — 2026-10-06 r3

Authorization: user directly requested「建置並發布 接著我會再測試一次」.
Status: rebuilt and published as prerelease on 2026-10-06T02:45:33Z,
Release ID 404256924. Exact public assets/discovery and all 20 anonymous
full-file SHA256 checks plus B signature admission passed. On 2026-10-06,
the user confirmed successful updating to 3.7.17; actual About update acceptance
passed (user reported). Settings retention and reboot remain pending; clean VM
acceptance remains deferred by the user.

- A 3.7.16 source `748c445380096c1df18569586e494f68f23c8875`;
  tag `acceptance-20261006-r3-a`.
- B 3.7.17 source `a890c2f4c7ba83d4fbc5703e0be50f158c9c0206`;
  tag/Release `acceptance-20261006-r3`.
- HEAD remains `b3422eb04bcdbb58300642498322e5aa458d205c`; normal index
  and unrelated `.tmp/` changes are preserved. A/B trees differ only in version.
- Both stable launchers must contain the 120-second shared startup policy and
  final health sample; retain 600-second preparation, signature verification,
  identity checks and safe rollback. Updating only B does not repair r2's host.
- One disposable isolated signing authority for final A/B. Verify and destroy
  its private key before upload. Use existing builders and admitted local inputs.
- B Setup and About use identical B bundle bytes from B source/tag. Public
  catalog changes only the immutable B bundle download URL.
- Publish as prerelease after fixed-source tests, exact installed-wheel probes,
  packaged smoke/extraction and asset gates. Keep production latest v3.7.8 and
  all four existing acceptance releases unchanged.
- Upload exactly 20 assets: 4 Setup/bundles, 8 A/B catalog/provenance/smoke/
  extraction proofs, 2 notices archives, catalog, public keyring, pair proof,
  helper, release body and SHA256SUMS. Private keys and mutable build roots are
  excluded.
- Verify anonymous public API asset names/size/SHA256, catalog discovery and
  downloaded bundle admission; actual About, settings/reboot and VM gates remain
  separate device acceptance.

Build evidence: `artifacts/about-health-timeout-20261006/`.
Final pair: `artifacts/installer-acceptance-pair-20261006-r3/`.
Public assets: `artifacts/github-acceptance-20261006-r3/`.
[Device runbook](../testing/github-acceptance-about-20261006-r3.md).
