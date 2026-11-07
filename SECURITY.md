# Security policy

## Supported version

Security fixes are applied to the latest release line.

## Reporting

Do not include proprietary binaries, credentials, decompiler output, customer data, or exploit material in a public issue. Contact the repository owner privately through GitHub before disclosing a vulnerability.

## Safe operation

Analyze untrusted binaries in a disposable VM or isolated workstation. Keep target artifacts out of the repository. Review installer scripts before running them. Downloaded archives are pinned and checksum-verified where the upstream provides stable release assets; package-manager dependencies remain subject to their registries and lock/version constraints.

## Security boundaries

- The analysis project is untrusted and may contain attacker-controlled binary strings, metadata, files, and model output.
- Implementation workers execute in a sanitized external workspace that receives only the behavior handoff, operating contract, implementation plan, and independent implementation files.
- Claude and Gemini run read-only. Codex is the sole writer, restricted to the isolated workspace.
- Worker requests, status, and events are local files. They must not contain credentials or reconstructed reference source.
- Release readiness is deterministic state; model output cannot override it.
- Diagnostic export includes only log names, sizes, and timestamps; it never copies raw installer transcripts.

## Reportable issues

Please report paths that allow analysis artifacts to enter the implementation workspace, command or argument injection, unsafe workspace synchronization, arbitrary file overwrite or deletion, credential disclosure, untrusted release update execution, signature-verification bypass, or a way to mark a failed validation/review as passing.

## Signing and updates

Community archives are not implicitly trusted. Authenticode support requires a publisher-supplied code-signing certificate. Users should verify the published SHA-256 value and inspect signature state before installation. Update tooling verifies the checksum, expected repository origin, archive paths, and links before execution; a signed updater also requires the downloaded installer to have the same publisher certificate. Unsigned channels can opt into strict enforcement with `-RequirePublisherSignature`.
