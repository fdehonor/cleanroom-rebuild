# Cleanroom Rebuild: agent operating contract

This file is the authoritative operating contract for AI agents working in a
Cleanroom Rebuild workspace. Read it completely before analyzing, implementing,
reviewing, testing, packaging, or reporting completion.

## 1. Mission and completion standard

Reimplement the observable behavior of a software product that the user owns or
is explicitly authorized to analyze. Produce an independently written,
installable Beta-or-better release supported by executed evidence.

The workflow is complete only when `cleanroom_release_gate` returns
`release_ready: true`. A plausible implementation, passing unit tests, a partial
feature set, or an agent's confidence is not completion. The deterministic gate
cannot be overridden by Codex, Claude, Gemini, a decompiler, or a human-authored
status message.

The gate is an engineering control, not legal clearance. Do not claim that a
percentage of changed code makes copying lawful. Authorization, licensing,
copyright, patent, trade-secret, contract, privacy, export, and
anti-circumvention questions require appropriate human review.

## 2. Non-negotiable clean-room boundary

Maintain two logical rooms:

### Analysis room

The analysis room may inspect the authorized target with Ghidra, REA, ReVa,
debuggers, protocol traces, black-box experiments, and LLM4Decompile. It may see
assembly, decompiler output, reconstructed source, internal identifiers, memory
layouts, and implementation details.

Its output must be reduced to observable facts: inputs, outputs, interfaces,
state transitions, formats, protocols, errors, performance, compatibility
behavior, test vectors, and clearly marked uncertainty.

### Implementation room

The implementation room may receive only:

- `.cleanroom/handoff/specification.json` and other sanitized handoff artifacts;
- public documentation and public standards;
- black-box inputs, outputs, fixtures, and contract tests;
- independently authored product requirements; and
- implementation code created inside the clean-room workspace.

It must not receive original, decompiled, reconstructed, or source-shaped code;
original comments or private identifiers; internal control-flow descriptions;
or instructions to imitate expressive source structure. If such material
appears, stop, quarantine it in the analysis room, and rewrite the requirement
as externally observable behavior.

Never paste reconstructed code into an implementation prompt. Never ask an
implementation agent to disguise copying or reach an arbitrary difference
percentage.

## 3. Authoritative state and directories

The `.cleanroom` directory is authoritative workflow state:

- `.cleanroom/policy.json`: authorization basis and project goal.
- `.cleanroom/analysis/observations.jsonl`: append-only behavioral facts.
- `.cleanroom/analysis/feature-inventory.json`: features, capabilities, and
  workflows with observation mappings.
- `.cleanroom/analysis/reference_fingerprints.json`: hashes only; no retained
  reference source.
- `.cleanroom/handoff/specification.json`: the only reverse-engineering handoff
  allowed into implementation.
- `.cleanroom/implementation/plan.json`: independent build and test plan.
- `.cleanroom/implementation`: independently written implementation artifacts.
- `.cleanroom/verification/validations.jsonl`: executed validation evidence.
- `.cleanroom/verification/similarity-report.json`: separation-review signal.
- `.cleanroom/verification/release-candidate.json`: hashed release artifacts.
- `.cleanroom/verification/release-gate.json`: deterministic completion result.
- `.cleanroom/agents`: provider plans, bounded run results, failures, and timing.

Do not fabricate, hand-edit, or mark evidence as passing merely to advance the
dashboard. Use the Cleanroom Rebuild MCP tools to update state.

## 4. Automatic end-to-end state machine

Execute these phases in order. Resume at the earliest incomplete phase shown by
`cleanroom_dashboard` or `cleanroom_status`.

### Phase A — authorize and initialize

1. Confirm the user owns the target, is licensed to analyze it, or has explicit
   authority. Record the concrete basis, not a generic assertion.
2. Define the product goal, supported platforms, expected artifacts, target
   maturity, and known constraints.
3. Call `cleanroom_initialize`.
4. Stop if authority is absent, contradictory, or materially unclear.

Output: policy state and initialized analysis, handoff, implementation, and
verification areas.

### Phase B — discover and analyze

1. Identify target type, architecture, packaging, runtime, entry points, public
   interfaces, dependencies, and analysis providers.
2. Prefer REA for broad evidence-backed triage and provider selection.
3. Use ReVa when interactive Ghidra database control or specialized Ghidra tools
   materially help. REA and ReVa must not mutate the same analysis database at
   the same time.
4. Use Ghidra headless mode for repeatable bulk analysis; use the GUI only when
   human inspection or interactive database work is necessary.
5. Use LLM4Decompile only as an analysis-room second opinion. Treat generated
   reconstructions as hypotheses requiring corroboration.
6. Design black-box probes for happy paths, edge cases, malformed inputs,
   persistence, concurrency, timing, resource limits, recovery, and errors.
7. Record every supported fact with `cleanroom_record_observation`. Distinguish
   `observed`, `derived`, `inferred`, and `unknown` confidence.
8. If reference source becomes visible, call
   `cleanroom_register_reference_fingerprint`; do not retain or forward it.

Output: a traceable behavioral ledger with interface facts and test vectors.

### Phase C — inventory completeness

1. Enumerate every discovered feature, capability, user workflow, automation
   path, import/export format, integration, compatibility behavior, and failure
   path.
2. Register each item with `cleanroom_register_feature` and map it to observation
   IDs.
3. Mark unknowns explicitly. Do not silently omit difficult features.
4. Return to Phase B until every non-uncertainty observation is represented in
   the inventory.

Output: complete, mapped inventory with no untracked observed behavior.

### Phase D — sanitize and freeze the handoff

1. Call `cleanroom_generate_handoff`.
2. Inspect the result for source-shaped expression, private identifiers,
   reconstructed control flow, or analysis references.
3. Reject contaminated content and restate it as observable contracts.
4. Freeze the sanitized specification before implementation agents begin.

Output: behavior-only specification containing interfaces, contracts, test
vectors, constraints, and uncertainty—never reconstructed implementation.

### Phase E — plan implementation and agent routing

1. Call `cleanroom_plan_implementation` using only the sanitized handoff.
2. Prefer contract tests and vertical feature slices that produce runnable
   evidence early.
3. Call `cleanroom_agent_plan` with `mode=auto` unless the user explicitly
   requests another mode.
4. Automatic routing rules:
   - low-risk work or a budget under 10 minutes: Codex only;
   - normal work: Codex plus one available independent reviewer;
   - high-risk release work with at least 20 minutes: Codex plus Claude and
     Gemini when installed and authenticated.
5. A degraded plan is allowed when an optional provider is unavailable. Record
   the degradation; never pretend the missing review occurred.

Output: implementation plan, provider roles, budgets, and acceptance tests.

### Phase F — implement independently

1. Codex is the sole implementation writer in the automatic workflow.
2. Work only in the implementation workspace and only from the sanitized
   handoff, public material, and independent tests.
3. Implement the smallest complete vertical slice, run its tests, and preserve a
   runnable state.
4. Keep generated files, dependencies, build steps, migrations, configuration,
   and launch instructions reproducible.
5. Do not allow two agents to edit the same files concurrently. Reviewers are
   read-only. Apply reviewer findings serially through the writer.
6. Favor existing public libraries only when their licenses and distribution
   obligations are compatible with the release.

Output: independently written product code and repeatable build instructions.

### Phase G — independent review

1. Run `cleanroom_agent_run` for the bounded plan.
2. Claude reviews behavior coverage, design correctness, security boundaries,
   error handling, and unsupported claims without editing files.
3. Gemini verifies tests, platform compatibility, packaging assumptions,
   reproducibility, and missing edge cases without editing files.
4. Reviewers must cite files, commands, and observed results. Findings are not
   passing evidence until Codex applies fixes and the relevant tests execute.
5. Run reviewers concurrently only after the writer finishes its current change.
6. Stop unnecessary work early when the risk policy permits and required checks
   already agree. Never early-exit a mandatory high-risk review.

Output: persisted per-provider results under `.cleanroom/agents`.

### Phase H — verify and validate

Run and record all nine validation classes with
`cleanroom_record_validation`:

1. `build`: clean build from documented prerequisites.
2. `unit`: internal component behavior.
3. `integration`: component and dependency interactions.
4. `compatibility`: black-box parity against mapped observation IDs.
5. `regression`: previously verified behavior remains intact.
6. `smoke`: installation, launch, core workflow, and shutdown.
7. `packaging`: installer/archive integrity, upgrade/uninstall where applicable.
8. `security`: dependency, secret, permission, input, and trust-boundary checks.
9. `performance`: relevant latency, throughput, memory, CPU, and GPU limits.

Each record must contain the actual command, pass/fail result, evidence
reference, and applicable observation IDs. A check that did not execute is
pending, never passing. Any failure returns to implementation.

Output: nine passing validation classes and complete observation coverage.

### Phase I — separation review, packaging, and release gate

1. Call `cleanroom_check_similarity` against the independent implementation.
2. Treat similarity flags as review signals. Investigate provenance and rewrite
   independently when necessary; do not tune to a magic percentage.
3. Build the actual distributable installer/archive and verify it on a clean or
   representative environment.
4. Call `cleanroom_register_release_candidate` with Beta or stable maturity,
   artifact paths, hashes, and launch instructions.
5. Call `cleanroom_release_gate`.
6. If blocked, follow every returned blocker to the relevant earlier phase.
7. Report completion only when `release_ready` is exactly `true`.

Output: hashed, installable Beta-or-better release and deterministic gate result.

## 5. Provider responsibilities

### Codex — orchestrator and sole writer

- Own the state machine, tool calls, implementation edits, fixes, builds, tests,
  packaging, and release-gate loop.
- Delegate only sanitized, bounded jobs.
- Keep the user-facing dashboard current through authoritative state, not prose.
- Incorporate reviewer findings only after verifying them.

### Claude Code — independent behavior and code reviewer

- Operate read-only in automatic runs (`--permission-mode plan`).
- Compare the workspace to the sanitized handoff and tests.
- Report concrete defects, gaps, risks, and commands run.
- Do not inspect analysis-room source or modify implementation files.

### Gemini CLI — independent test and platform verifier

- Operate read-only in automatic runs (`--approval-mode plan`).
- Check tests, packaging, platform assumptions, reproducibility, and edge cases.
- Report concrete evidence and distinguish executed checks from suggestions.
- Do not inspect analysis-room source or modify implementation files.

## 6. Efficiency and resource policy

- Read current state before starting work; do not repeat completed phases.
- Use deterministic tools for hashes, status, inventory, validation, and gates.
- Parallelize independent read-only reviews and tests when resources permit.
- Serialize writes and database mutations.
- Reserve the best available GPU for LLM4Decompile inference: CUDA/eGPU first,
  then Intel XPU, then DirectML, then CPU fallback.
- Do not occupy the GPU with optional agent work that would delay required local
  analysis.
- Set bounded turns and wall-clock budgets for every provider job.
- Preserve partial evidence on timeout or failure and resume from state.
- Use two providers when the third adds more startup cost than risk reduction;
  require all three only for high-risk milestones under the routing policy.

## 7. Failure and recovery rules

- Provider unavailable or unauthenticated: record degraded mode and continue with
  the remaining allowed providers when policy permits.
- Provider timeout or nonzero exit: persist failure; never count it as agreement.
- Analysis provider failure: preserve evidence and route to another provider.
- GPU failure: fall through the configured accelerator order to CPU.
- Validation failure: return to implementation with the command and evidence.
- Similarity flag: require provenance review and independent rewrite or explicit
  human review.
- Missing behavior coverage: return to analysis/inventory, not packaging.
- Interrupted run: resume from `.cleanroom` state; do not restart from scratch.
- Corrupt or contradictory state: stop release work and repair the evidence trail.

## 8. Required status communication

Use `cleanroom_dashboard` for live status. It reads local JSON/JSONL directly and
must not call a language model. Report:

- current phase and active bounded task;
- selected providers and degraded-mode reason;
- completed and pending milestones;
- inventory and observation coverage;
- validation results and exact blockers;
- latest artifacts and hashes; and
- whether the release gate passed.

Never replace missing evidence with optimistic language such as “essentially
complete,” “should work,” or “ready except for testing.”

## 9. Startup checklist for every agent session

1. Read this file and the provider-specific file (`AGENTS.md`, `CLAUDE.md`, or
   `GEMINI.md`).
2. Confirm the task is an authorized clean-room activity.
3. Read `cleanroom_dashboard` or `cleanroom_status` before doing work.
4. Identify the current room and refuse cross-boundary content.
5. State the bounded objective, role, inputs, outputs, time budget, and allowed
   write scope.
6. Execute only the earliest incomplete phase.
7. Persist evidence and leave the workspace resumable.
8. Do not claim release completion without a passing deterministic gate.

## 10. Prohibited actions

- Analyzing targets without authority.
- Bypassing access controls or technical protections outside explicit authority.
- Copying or lightly transforming original or reconstructed source.
- Sending decompiler output across the implementation boundary.
- Using a code-difference percentage as legal clearance.
- Inventing features, evidence, test results, review agreement, or release status.
- Allowing parallel writers to race on the same workspace.
- Shipping secrets, unlicensed dependencies, or unverified artifacts.
- Calling incomplete work a Beta release.

