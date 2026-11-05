---
name: cleanroom-rebuild
description: Use for authorized clean-room reconstruction, interoperability analysis, behavior-only reverse-engineering handoffs, and independent reimplementation planning.
---

# Clean-room rebuild workflow

Use this workflow only for software the user owns, is licensed to analyze, or is otherwise authorized to inspect. It is an engineering control, not legal clearance.

## Separation model

Maintain two logical rooms:

1. The analysis room may use REA, ReVa/Ghidra, and LLM4Decompile. It may inspect binaries and decompiler output.
2. The implementation room must not receive decompiled source, reconstructed source, original identifiers, comments, internal layout, or source-shaped control flow. It receives only the engine's behavior-only handoff, public documentation, black-box test vectors, and independently written requirements.

Do not use a percentage-of-difference rule. Similarity checks are review signals, not legal conclusions.

## Efficient orchestration

1. Open `cleanroom_dashboard` whenever the user asks for status or wants the live view. It reads authoritative local workflow state and refreshes without invoking a language model.
2. Call `cleanroom_initialize` with the authorization basis and product goal.
3. Prefer REA for broad evidence-backed triage and provider selection. Use ReVa when interactive Ghidra database control or its specialized tools materially improve the analysis. Do not have both mutate the same analysis database concurrently.
4. Use LLM4Decompile only as a second opinion: `llm4decompile_refine` for Ghidra pseudocode or `llm4decompile_assembly` for assembly. Never pass its reconstructed code into the implementation room.
5. Record only observable facts with `cleanroom_record_observation`. Keep statements compact and attach interface facts and black-box test vectors.
6. When reference code is visible in the analysis room, call `cleanroom_register_reference_fingerprint`; the engine stores hashes, not the code.
7. Call `cleanroom_generate_handoff`, then `cleanroom_plan_implementation`. Begin implementation from those artifacts in `.cleanroom/handoff` and `.cleanroom/implementation`.
8. Call `cleanroom_agent_plan` before implementation. Prefer `mode=auto`: one agent for low-risk short work, Codex plus one reviewer for normal work, and all three providers for high-risk release milestones when the time budget permits. Use `cleanroom_agent_run` to execute the bounded plan. Codex is the sole writer; Claude and Gemini are independent read-only reviewers.
9. Validate behavior with tests derived from the handoff. Record executed evidence with `cleanroom_record_validation`, register the built artifacts with `cleanroom_register_release_candidate`, and call `cleanroom_check_similarity`.
10. Call `cleanroom_release_gate`. Do not describe the work as complete unless it returns `release_ready: true`. Partial implementations, unexecuted tests, missing release artifacts, and unresolved similarity flags are incomplete.

## Handoff quality

Capture inputs, outputs, state transitions, timing and resource limits, errors, persistence, protocols, file formats, compatibility quirks, and uncertainty. Separate observations from inferences. Prefer stable identifiers and hashes for provenance.

If the user asks to disguise copying, evade a license, bypass access controls without authority, or hit an arbitrary code-difference percentage, stop that part and redirect to independently specified behavior and legal review.
