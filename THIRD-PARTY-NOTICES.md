# Third-party notices

Cleanroom Rebuild's installer and original orchestration code are MIT licensed. The installer downloads the following independent components; each remains governed by its upstream terms.

| Component | Pinned release | License/terms | Upstream |
|---|---:|---|---|
| LLM4Decompile code | repository clone | MIT | https://github.com/albertan017/LLM4Decompile |
| LLM4Decompile model weights | 1.3B V1.5/V2 | DeepSeek Model License 1.0 with use restrictions | https://huggingface.co/LLM4Binary |
| Ghidra | 12.1.3 | Apache-2.0 plus included third-party notices | https://github.com/NationalSecurityAgency/ghidra |
| Reverse Engineering Assistant (ReVa) | 7.3.1 | Apache-2.0 | https://github.com/cyberkaida/reverse-engineering-assistant |
| REA | 6.8.0 | MIT | https://github.com/morluto/rea |
| Eclipse Temurin JDK | 21.0.13+9 | GPL-2.0 with Classpath Exception and included notices | https://adoptium.net/ |
| Apache Ant | 1.10.18 | Apache-2.0 | https://ant.apache.org/ |
| Python | 3.15 global; 3.12 GPU worker | PSF License | https://www.python.org/ |
| PyTorch and TorchVision | package-manager versions shown in installer log | BSD-style upstream licenses | https://pytorch.org/ |
| Transformers and Accelerate | Transformers 4.55.3 for GPU worker | Apache-2.0 | https://github.com/huggingface/transformers |
| Torch-DirectML | 0.2.5 development build via PyPI | MIT | https://github.com/microsoft/DirectML |
| Visual Studio Code | current winget release | Microsoft license terms | https://code.visualstudio.com/ |
| Visual Studio Community | optional current winget release | Microsoft Visual Studio license terms and Community eligibility limits | https://visualstudio.microsoft.com/ |
| PyCharm Community / IntelliJ IDEA Community | optional current winget releases | JetBrains and bundled component terms | https://www.jetbrains.com/ |
| LLVM, CMake, Ninja | current winget releases | Their respective open-source licenses | https://llvm.org/ |

Exact upstream license files for the three requested projects and Ghidra are included in `third-party-licenses/`. Package-manager dependencies may add transitive licenses; their installed metadata and the installer log are authoritative for the resolved versions.

The installer does not bundle Ghidra, Java, model weights, npm packages, or Python wheels. It obtains them from their official upstream distribution locations and verifies fixed SHA-256 checksums for the manually downloaded release archives.

No upstream project endorses Cleanroom Rebuild. Product and project names are used only for identification.
