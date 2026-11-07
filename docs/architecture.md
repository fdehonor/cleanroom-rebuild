# End-to-end process and control chart

This chart distinguishes the orchestration plane, evidence plane, clean-room boundary, implementation plane, verification plane, and model-free observability plane. Solid arrows are the normal automatic path. Dashed arrows are recovery or review loops.

```mermaid
flowchart TB
    U[Authorized user supplies target and goal] --> A0{Authorization basis recorded?}
    A0 -- No --> STOP[Stop: request authority and scope]
    A0 -- Yes --> INIT[Initialize project and evidence ledger]

    subgraph ORCH[Orchestration plane: Codex skill and MCP tools]
      INIT --> DISCOVER[Discover target type, interfaces, and analysis providers]
      DISCOVER --> ROUTE{Choose analysis path}
      ROUTE -->|Native binary| REA[REA broad triage]
      ROUTE -->|Interactive database work| REVA[ReVa MCP]
      ROUTE -->|Managed/mobile/web| ALT[REA managed, mobile, browser, or runtime providers]
      REA --> GHIDRA[Ghidra headless or GUI analysis]
      REVA --> GHIDRA
      ALT --> OBS
      GHIDRA --> LLM{Reconstruction second opinion useful?}
      LLM -- Yes --> DECOMP[LLM4Decompile in analysis room only]
      LLM -- No --> OBS[Record observable facts]
      DECOMP --> OBS
    end

    subgraph EVIDENCE[Evidence plane: authoritative local state]
      OBS --> LEDGER[(Behavior observations JSONL)]
      OBS --> FP[(Hashed reference shingles; no raw source retained)]
      LEDGER --> INV[Feature, capability, and workflow inventory]
      INV --> COVER{Every observed behavior mapped?}
      COVER -- No --> DISCOVER
      COVER -- Yes --> FREEZE[Freeze behavior-only specification]
    end

    subgraph BOUNDARY[Clean-room boundary]
      FREEZE --> FILTER{Source-shaped expression present?}
      FILTER -- Yes --> REJECT[Reject and rewrite as observable behavior]
      REJECT -.-> OBS
      FILTER -- No --> HANDOFF[(Sanitized handoff: interfaces, behavior, tests)]
    end

    subgraph IMPLEMENT[Independent implementation plane]
      HANDOFF --> PLAN[Generate implementation and contract-test plan]
      PLAN --> ROUTER{Risk, installed providers, and time budget}
      ROUTER -->|Low risk or under 10 min| C1[Codex only]
      ROUTER -->|Normal work| C2[Codex writer plus one reviewer]
      ROUTER -->|High risk and 20+ min| C3[Codex writer plus Claude and Gemini reviewers]
      C1 & C2 & C3 --> QUEUE[Queue detached worker and live event stream]
      QUEUE --> ISOLATE[Create sanitized external directory without analysis artifacts]
      ISOLATE --> OSBOUND{Attested disposable VM or audited wrapper active?}
      OSBOUND -->|No| STOPRUN[Block every automatic execution and release readiness]
      OSBOUND -->|Yes| IDE
      IDE --> TESTFIRST[Create black-box contract tests]
      TESTFIRST --> BUILD[Codex implements independent code and assets]
      BUILD --> ARTIFACT[Build runnable candidate]
      ARTIFACT --> REVIEW[Parallel structured read-only reviews]
      REVIEW -->|Medium or higher findings| REPAIR[Bounded Codex repair cycle]
      REPAIR --> REVIEW
      REVIEW -->|Approved| SYNC[Sync implementation directory only]
    end

    subgraph VERIFY[Verification and release plane]
      SYNC --> SIM[Compare implementation to hashed reference fingerprints]
      SIM --> FLAG{Similarity review flags?}
      FLAG -- Yes --> HUMAN[Human separation review and independent rewrite]
      HUMAN -.-> BUILD
      FLAG -- No --> PACKAGE[Build and hash Beta-or-better release artifacts]
      PACKAGE --> REGISTER[Register immutable candidate manifest]
      REGISTER --> MATRIX{Nine validation classes bound to candidate digest}
      MATRIX --> V1[Build]
      MATRIX --> V2[Unit]
      MATRIX --> V3[Integration]
      MATRIX --> V4[Compatibility]
      MATRIX --> V5[Regression]
      MATRIX --> V6[Smoke]
      MATRIX --> V7[Packaging]
      MATRIX --> V8[Security]
      MATRIX --> V9[Performance]
      V1 & V2 & V3 & V4 & V5 & V6 & V7 & V8 & V9 --> ALLPASS{All executed checks pass?}
      ALLPASS -- No --> BUILD
      ALLPASS -- Yes --> GATE{Hard release gate rehashes candidate}
      GATE -- Missing feature, evidence, coverage, or artifact --> BLOCK[Block release and list exact blockers]
      BLOCK -.-> DISCOVER
      BLOCK -.-> BUILD
      GATE -- All requirements satisfied --> RELEASE[Verified working Beta/stable release]
    end

    subgraph OBSERVE[Model-free observability plane]
      STATE[(Project JSON and JSONL files)] --> DASH[Codex live status app]
      DASH --> POLL[Read-only poll every 2 seconds]
      POLL --> DASH
      DASH --> VIEW[Steps, percent, inventory, coverage, validations, blockers, artifacts, GPU]
    end

    INIT --> STATE
    LEDGER --> STATE
    INV --> STATE
    HANDOFF --> STATE
    PLAN --> STATE
    MATRIX --> STATE
    SIM --> STATE
    PACKAGE --> STATE
    GATE --> STATE

    subgraph RESILIENCE[Runtime resilience]
      GPU{Accelerator available?} -->|CUDA or eGPU| CUDA[GPU-first with CPU layer offload]
      GPU -->|Intel XPU| XPU[Intel accelerator]
      GPU -->|DirectML device or eGPU| DML[DirectML]
      GPU -->|No supported GPU| CPU[CPU fallback]
      PROVIDER{Analysis provider fails?} --> FALLBACK[Preserve evidence; retry or route to alternate provider]
    end
```

## State machine

```mermaid
stateDiagram-v2
    [*] --> Authorized
    Authorized --> Analyzing: project initialized
    Analyzing --> Specified: observations mapped and handoff frozen
    Specified --> Implementing: independent plan approved
    Implementing --> Validating: runnable candidate built
    Validating --> Implementing: any validation fails
    Validating --> SeparationReview: all validation classes pass
    SeparationReview --> Implementing: similarity flag requires rewrite
    SeparationReview --> Packaging: review clear
    Packaging --> Gated: Beta/stable artifacts hashed
    Gated --> Analyzing: missing feature or behavior coverage
    Gated --> Implementing: implementation or test blocker
    Gated --> Released: all hard requirements pass
    Released --> [*]
```

## Automation invariants

1. Decompiler or reconstructed source never crosses into the implementation handoff.
2. The dashboard is read-only and does not call a language model.
3. A failed or absent check is never treated as passing.
4. Every non-uncertainty observation must map to inventory and compatibility evidence.
5. Release artifacts are hashed and must be at least Beta maturity.
6. Similarity results are review signals, never legal clearance.
