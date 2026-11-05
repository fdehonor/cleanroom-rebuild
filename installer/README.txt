CLEANROOM REBUILD 0.3.0 — PUBLIC WINDOWS INSTALLER

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

How to install
--------------
1. Keep this entire folder together.
2. Double-click "Install Cleanroom Rebuild.cmd".
3. Review the displayed third-party terms and type AGREE if you accept them.
4. Wait for the green READY message. Large downloads can take time.
5. Close and reopen Codex.
6. In Codex, ask:
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

Public-use boundary
-------------------
Free availability does not grant permission to analyze third-party software.
Users are responsible for authorization, licenses, contracts, privacy, export,
patent, copyright, trade-secret, and anti-circumvention requirements.

Optional proprietary providers
------------------------------
REA can also use IDA, Hopper, Kuna, and JADX when separately installed and licensed.
They are not required for the included Ghidra workflow and are not bundled.
