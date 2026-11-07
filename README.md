# Cleanroom Rebuild

Cleanroom Rebuild is a Windows-first Codex plugin and installer for authorized, evidence-driven clean-room reimplementation. It coordinates Ghidra, ReVa, REA, and LLM4Decompile; enforces a behavior-only handoff; configures a coding workspace; and blocks release until a Beta-or-better artifact has complete engineering evidence.

## What is included

- A 21-tool local MCP server for clean-room project state, evidence, asynchronous multi-agent scheduling, engine-executed validation, similarity review, and release gating.
- A zero-LLM live status app that opens from Codex navigation or a conversation and polls local state every two seconds.
- GPU-first LLM4Decompile inference with CUDA/eGPU, Intel XPU, DirectML, and CPU fallback.
- A one-click installer for Ghidra/ReVa, REA, model runtime, and Codex registration.
- VS Code/Cursor/Windsurf setup with the official Codex extension and a ready multi-repository workspace.
- Optional Visual Studio Community, PyCharm Community, and IntelliJ IDEA Community setup.
- Automatic provider routing: Codex writes; Claude Code and Gemini CLI perform bounded, parallel read-only reviews when risk and time justify them.
- A detailed `CLEANROOM_WORKFLOW.md` operating contract is installed in the IDE workspace and copied into every initialized project, with provider-specific `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` instructions.
- Sanitized external implementation workspaces, live job events, cancellation/resume, structured reviewer findings, and bounded automatic repair cycles. On supported Windows editions, implementation commands run in disposable Hyper-V-isolated Windows Sandbox VMs with per-command attestations.
- Pinned model-worker dependencies, generated SBOMs, repair/uninstall tools, redacted diagnostics, and optional Authenticode release signing.

## Install

Download a release archive, extract it, and double-click `Install Cleanroom Rebuild.cmd`. The standard profile installs the recommended VS Code environment. `Install Full IDE Suite.cmd` additionally installs the larger Visual Studio and JetBrains environments.

Restart Codex after installation. Open **Clean-room Live Status** from the plugin navigation, or start with:

> Start an authorized clean-room rebuild project, analyze the supplied binary with Ghidra, inventory every observable feature and workflow, and continue until the Beta release gate passes.

The installer also installs the Claude Code and Gemini CLIs by default. Run `claude` and `gemini` once to complete their separate account sign-ins. The system remains usable with Codex alone; normal work selects two available providers, short low-risk work selects one, and high-risk release work selects all three when installed and within the time budget.

## Architecture and automation

See [the detailed process and control chart](docs/architecture.md) and [the automation contract](docs/automation-contract.md).

Maintenance scripts are installed under `~/Tools/Cleanroom-Rebuild/maintenance`. Public release archives remain unsigned unless the publisher supplies a trusted code-signing certificate and runs `Sign-Release.ps1` before packaging.

Directory separation alone is not described as an OS security boundary. The default `CLEANROOM_SANDBOX_BACKEND=auto` selects Windows Sandbox on supported Windows 10/11 Pro, Enterprise, or Education systems when the optional feature and hypervisor are ready. Every automatic execution requires an enforced backend. Each command gets a fresh disposable VM and a separate low-privilege guest principal. Reviewer workspaces are read-only. Only the selected provider's minimum authentication seed is supplied; validation commands receive no provider credentials and no network. Clipboard, vGPU, audio/video input, and printers are disabled. Provider jobs retain API networking. Every VM command emits a hashed runtime attestation, and release validations are bound to an immutable candidate manifest.

Run `Enable Secure Sandbox.cmd` from the installed maintenance folder to enable the optional Windows feature with elevation, then restart if requested. Windows Home cannot host Windows Sandbox; it fails closed for release work. Such systems must upgrade Windows or use `CLEANROOM_ENFORCED_SANDBOX_WRAPPER` with an independently audited wrapper accepting `--workspace <path> -- <command...>`. The legacy wrapper path is still live-canary attested.

## Important boundary

This project does not grant permission to analyze third-party software, bypass access controls, or ship infringing work. The release gate verifies engineering evidence, not legal clearance. Use only targets you own or are explicitly authorized to analyze and obtain qualified legal review for release decisions.

## License

Original installer and plugin code are MIT licensed. Downloaded tools and model weights retain their own terms; see [third-party notices](THIRD-PARTY-NOTICES.md). The LLM4Decompile model weights are subject to the DeepSeek Model License and its use restrictions.
