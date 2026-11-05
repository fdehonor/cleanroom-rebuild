# Security policy

## Supported version

Security fixes are applied to the latest release line.

## Reporting

Do not include proprietary binaries, credentials, decompiler output, customer data, or exploit material in a public issue. Contact the repository owner privately through GitHub before disclosing a vulnerability.

## Safe operation

Analyze untrusted binaries in a disposable VM or isolated workstation. Keep target artifacts out of the repository. Review installer scripts before running them. Downloaded archives are pinned and checksum-verified where the upstream provides stable release assets; package-manager dependencies remain subject to their registries and lock/version constraints.
