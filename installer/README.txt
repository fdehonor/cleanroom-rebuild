CLEANROOM REBUILD 0.6.0 — PUBLIC WINDOWS INSTALLER

This installer may be used free of charge under its MIT License. Components it
downloads retain their own licenses. Read THIRD-PARTY-NOTICES.md first.

What it installs
----------------
- LLM4Decompile runtime and source
- Ghidra 12.1.3 + ReVa 7.3.1
- REA 6.8.0 and its Codex skill
- Cleanroom Rebuild Codex plugin and hard Beta release gate
- GPU-first inference with CPU fallback and automatic eGPU discovery
- A ready coding workspace with the official Codex extension and IDE tasks
- A model-free live status app in Codex with two-second progress refresh
- Codex, Claude Code, and Gemini CLI automatic task routing
- A detailed shared LLM operating contract with provider-specific instructions
- Sanitized external implementation workspaces and asynchronous live job events
- Disposable Hyper-V Windows Sandbox implementation workers with attestations
- Cancellation, resume, structured reviews, and automatic repair cycles
- SBOM, repair, uninstall, redacted diagnostics, and optional signing tools

How to install
--------------
1. Keep this entire folder together.
2. Double-click "Install Cleanroom Rebuild.cmd".
3. Review the displayed third-party terms and type AGREE if you accept them.
4. Wait for the green READY message. Large downloads can take time.
5. Close and reopen Codex.
6. Run `claude` and `gemini` once if you want those optional reviewers, and
   complete each provider's separate sign-in.
7. In Codex, ask:
   Start a clean-room rebuild project and analyze my authorized binary with Ghidra.

IDE setup
---------
The standard installer installs/configures VS Code, the official Codex extension,
Python, C/C++, CMake, PowerShell, LLVM, Ninja, and a multi-repository workspace.
It also configures detected Cursor and Windsurf installations.

For Visual Studio Community plus C++/.NET workloads, PyCharm Community, and
IntelliJ IDEA Community, double-click "Install Full IDE Suite.cmd" instead.
This full option requires substantially more disk space and retains each IDE's
own license terms. Visual Studio receives a .vsconfig file; JetBrains IDEs receive
a shared Codex CLI run configuration.

Requirements
------------
- 64-bit Windows 10 or 11
- Codex desktop installed and signed in
- Internet access (Ghidra and the AI runtime are large downloads)
- Roughly 15 GB free before model weights; more if you download models

Strong isolation requirements
-----------------------------
Release-producing agent and validation runs require a supported Windows 10/11 Pro, Enterprise,
or Education with firmware virtualization and Windows Sandbox enabled. The installer
checks these prerequisites but does not silently weaken the release gate. Run
"Enable Secure Sandbox.cmd" as administrator, restart if requested, then run
Test-CleanroomIsolation.ps1. Windows Home users must upgrade or configure an
independently audited external sandbox wrapper.

Optional local model download
-----------------------------
The default install configures LLM4Decompile and downloads model weights on first use.
To pre-download both 1.3B models, run in PowerShell:

  .\Install-CleanroomRebuild.ps1 -DownloadModels

GPU behavior
------------
The latest Python remains your global Python. An isolated Python 3.12 worker is added
because current Windows DirectML wheels do not support Python 3.15. NVIDIA CUDA GPUs
and eGPUs are preferred and can spill layers to CPU RAM. Intel/AMD adapters use
DirectML when available. CPU remains the automatic fallback.

Clean-room and release policy
-----------------------------
Use only software you own or are authorized to analyze. The workflow separates
reverse-engineering observations from implementation, stores only hashed source
fingerprints for similarity review, and blocks release until the feature inventory,
compatibility coverage, nine validation classes, packaging, and a Beta-or-better
artifact all pass. These engineering checks are not legal clearance.

Agent efficiency
----------------
Codex is the only implementation writer. Normal work uses Codex plus one available
reviewer. Short low-risk jobs use Codex alone. High-risk release milestones use
Codex, Claude, and Gemini when installed and the time budget is at least 20 minutes.
Reviewers run in parallel, time out cleanly, and cannot override the release gate.
Implementation agents run outside the analysis project with only the sanitized
handoff and independent implementation files. Use `cleanroom_agent_cancel` and
`cleanroom_agent_resume` for interrupted work.

Directory separation is not an OS security boundary. By default, supported systems
use a new disposable Hyper-V Windows Sandbox VM for every implementation or
validation command. Only the sanitized workspace is writable. Runtime and minimal
provider bootstrap credentials are read-only seeds; clipboard and device sharing
are disabled. Provider API networking remains enabled. Runtime attestations are
hashed into the evidence chain and are mandatory at the release gate. An audited
external wrapper remains available for systems where Windows Sandbox cannot run.

Maintenance
-----------
Maintenance scripts and the pinned dependency lock are installed under
`%USERPROFILE%\Tools\Cleanroom-Rebuild\maintenance`. Use Repair-CleanroomRebuild.ps1
to repair the installation, Update-CleanroomRebuild.ps1 for checksum-verified
updates from the expected GitHub repository, Export-Diagnostics.ps1 to create a
credential-redacted support archive, and Uninstall-CleanroomRebuild.ps1 for confirmed removal. The
generated component inventory is `cleanroom-sbom.json`.

Release signing
---------------
The public source supports Authenticode signing through Sign-Release.ps1. A real
trusted signature requires the publisher's code-signing certificate and private
key; unsigned community builds must not claim to be signed.

Public-use boundary
-------------------
Free availability does not grant permission to analyze third-party software.
Users are responsible for authorization, licenses, contracts, privacy, export,
patent, copyright, trade-secret, and anti-circumvention requirements.

Optional proprietary providers
------------------------------
REA can also use IDA, Hopper, Kuna, and JADX when separately installed and licensed.
They are not required for the included Ghidra workflow and are not bundled.
