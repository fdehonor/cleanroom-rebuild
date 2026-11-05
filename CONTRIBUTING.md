# Contributing

Contributions must preserve the analysis/implementation separation boundary, must not add proprietary samples or reconstructed source, and must include tests for changes to state, validation, release gating, or UI resources.

Run:

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 -m py_compile plugin/server/cleanroom_mcp.py
```

Changes to the status UI require a versioned resource URI when they break cached compatibility. Installer changes must remain idempotent and must not silently install the optional full IDE suite.
