# Automation contract

## Expected inputs

- A target the user owns or has authority to analyze.
- A concrete product goal and supported platforms.
- Executable samples, public interfaces, fixtures, or black-box test access.
- Any contractual or technical constraints that affect analysis.

## Automatic responsibilities

The orchestration skill selects analysis providers, records sanitized observations, maintains the feature inventory, generates the implementation plan, tracks executed validation evidence, checks hashed-token similarity, registers release artifacts, and evaluates the hard gate. The IDE configurator prepares editor extensions, compiler/build tools, tasks, and a shared workspace.

`CLEANROOM_WORKFLOW.md` is the authoritative cross-provider instruction manual. The installer places it in the IDE workspace, and `cleanroom_initialize` copies the bundled, hashed version into `.cleanroom/CLEANROOM_WORKFLOW.md` for project-local use. Provider-specific files define roles and require the complete shared contract to be read before action.

The coding-agent scheduler detects Codex, Claude Code, and Gemini CLI without a model call. In automatic mode it chooses one provider for short/low-risk work, two for normal work, and three for high-risk work when at least 20 minutes are available. Codex is the only writer. Independent reviewers run concurrently and cannot approve or override the deterministic release gate. Missing or unauthenticated optional providers produce a visible degraded plan instead of blocking Codex-only operation.

The status application reads state directly from disk every two seconds. Its refresh path is `MCP App → cleanroom_dashboard → local JSON/JSONL`; it does not invoke Codex or another model.

## Intelligence boundaries

Codex and LLM4Decompile may assist analysis and implementation. Deterministic tools own authorization metadata, provenance, hashes, status, validation records, and release decisions. A model cannot override a failed gate, invent passing evidence, or mark an unverified inventory item complete.

## Recovery behavior

- Analysis-provider failure preserves prior evidence and permits routing to another provider.
- Unsupported GPU operations fall through the configured accelerator order to CPU.
- Failed validations route back to implementation with their command and evidence reference.
- Similarity flags require independent rewrite or explicit human review.
- Missing feature coverage routes back to discovery, not directly to packaging.
- A process interruption leaves append-only observations and validations on disk for resumption.
- Provider timeouts and nonzero exits are stored under `.cleanroom/agents`; a failed reviewer is never recorded as agreement.

## Completion definition

Completion requires every discovered inventory item to be verified, all non-uncertainty observations to have compatibility coverage, all nine validation classes to pass, similarity review to have no unresolved flags, a hashed Beta-or-stable artifact to exist, and `cleanroom_release_gate` to return `release_ready: true`.

This proves the configured engineering evidence is complete. It does not prove that undiscovered behavior does not exist or supply legal clearance.
