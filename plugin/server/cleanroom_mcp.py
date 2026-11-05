from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable


SERVER_NAME = "cleanroom-engine"
SERVER_VERSION = "0.3.0"
STATUS_RESOURCE_URI = "ui://cleanroom-rebuild/status-dashboard-v1.html"
TOKEN_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*|0x[0-9A-Fa-f]+|\d+(?:\.\d+)?|"
    r"==|!=|<=|>=|->|::|&&|\|\||<<|>>|[{}()\[\];,.+\-*/%&|^~<>?:=]"
)
SOURCE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".cs", ".go", ".java",
    ".js", ".jsx", ".ts", ".tsx", ".py", ".rb", ".rs", ".swift", ".kt",
    ".kts", ".php", ".scala", ".m", ".mm", ".asm", ".s",
}
MODEL_CACHE: dict[str, tuple[Any, Any, str, Any]] = {}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOLS = [
    {
        "name": "cleanroom_dashboard",
        "title": "Clean-room Live Status",
        "description": "Open the zero-LLM live workflow dashboard or return its authoritative status snapshot.",
        "inputSchema": _schema(
            {"project_root": {"type": "string"}},
            [],
        ),
        "annotations": {"readOnlyHint": True},
        "_meta": {
            "ui": {"resourceUri": STATUS_RESOURCE_URI, "visibility": ["app"]},
            "openai/ui": {
                "entrypoints": [{"type": "global"}, {"type": "thread"}],
                "availableDisplayModes": ["inline", "fullscreen", "pip"],
            },
            "openai/outputTemplate": STATUS_RESOURCE_URI,
        },
    },
    {
        "name": "cleanroom_initialize",
        "description": "Create an authorized clean-room project with separate analysis, handoff, implementation, and verification areas.",
        "inputSchema": _schema(
            {
                "project_root": {"type": "string"},
                "project_name": {"type": "string", "minLength": 1, "maxLength": 120},
                "product_goal": {"type": "string", "minLength": 1, "maxLength": 2000},
                "source_description": {"type": "string", "minLength": 1, "maxLength": 2000},
                "authorization_basis": {"type": "string", "minLength": 1, "maxLength": 2000},
            },
            ["project_root", "project_name", "product_goal", "source_description", "authorization_basis"],
        ),
    },
    {
        "name": "cleanroom_record_observation",
        "description": "Record a compact behavioral fact in the analysis room. Source-shaped code is rejected from the handoff path.",
        "inputSchema": _schema(
            {
                "project_root": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["interface", "behavior", "state", "format", "protocol", "error", "performance", "compatibility", "uncertainty"],
                },
                "statement": {"type": "string", "minLength": 1, "maxLength": 2000},
                "source_tool": {"type": "string", "minLength": 1, "maxLength": 120},
                "source_reference": {"type": "string", "minLength": 1, "maxLength": 2000},
                "confidence": {"type": "string", "enum": ["observed", "derived", "inferred", "unknown"]},
                "interfaces": {"type": "array", "items": {"type": "string", "maxLength": 500}, "maxItems": 100},
                "test_vectors": {"type": "array", "items": {"type": "string", "maxLength": 1000}, "maxItems": 100},
            },
            ["project_root", "category", "statement", "source_tool", "source_reference", "confidence"],
        ),
    },
    {
        "name": "cleanroom_register_reference_fingerprint",
        "description": "Hash reference-code token shingles without persisting the code, enabling later similarity review across the clean-room boundary.",
        "inputSchema": _schema(
            {
                "project_root": {"type": "string"},
                "reference_name": {"type": "string", "minLength": 1, "maxLength": 200},
                "language": {"type": "string", "minLength": 1, "maxLength": 80},
                "code": {"type": "string", "minLength": 1, "maxLength": 500000},
                "shingle_size": {"type": "integer", "minimum": 5, "maximum": 15, "default": 7},
            },
            ["project_root", "reference_name", "language", "code"],
        ),
    },
    {
        "name": "cleanroom_generate_handoff",
        "description": "Generate a behavior-only specification for the implementation room, excluding source references and reconstructed code.",
        "inputSchema": _schema(
            {"project_root": {"type": "string"}},
            ["project_root"],
        ),
    },
    {
        "name": "cleanroom_register_feature",
        "description": "Register or update one discovered feature, capability, or end-to-end workflow and map it to behavioral observations.",
        "inputSchema": _schema(
            {
                "project_root": {"type": "string"},
                "feature_id": {"type": "string", "minLength": 1, "maxLength": 120, "pattern": "^[A-Za-z0-9._-]+$"},
                "name": {"type": "string", "minLength": 1, "maxLength": 300},
                "kind": {"type": "string", "enum": ["feature", "capability", "workflow"]},
                "status": {"type": "string", "enum": ["discovered", "specified", "implemented", "verified"]},
                "observation_ids": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "minItems": 1, "maxItems": 1000},
                "evidence_reference": {"type": "string", "minLength": 1, "maxLength": 2000},
            },
            ["project_root", "feature_id", "name", "kind", "status", "observation_ids", "evidence_reference"],
        ),
    },
    {
        "name": "cleanroom_plan_implementation",
        "description": "Create an efficient implementation plan from the sanitized handoff specification.",
        "inputSchema": _schema(
            {
                "project_root": {"type": "string"},
                "constraints": {"type": "array", "items": {"type": "string", "maxLength": 500}, "maxItems": 100},
                "priorities": {"type": "array", "items": {"type": "string", "maxLength": 500}, "maxItems": 100},
            },
            ["project_root"],
        ),
    },
    {
        "name": "cleanroom_check_similarity",
        "description": "Compare implementation token shingles with hashed reference fingerprints. Results are review signals, not legal clearance.",
        "inputSchema": _schema(
            {
                "project_root": {"type": "string"},
                "implementation_path": {"type": "string", "default": ".cleanroom/implementation"},
                "review_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.08},
            },
            ["project_root"],
        ),
    },
    {
        "name": "cleanroom_record_validation",
        "description": "Record evidence from an executed release validation and map compatibility coverage to observation IDs.",
        "inputSchema": _schema(
            {
                "project_root": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["build", "unit", "integration", "compatibility", "regression", "smoke", "packaging", "security", "performance"],
                },
                "name": {"type": "string", "minLength": 1, "maxLength": 200},
                "passed": {"type": "boolean"},
                "command": {"type": "string", "minLength": 1, "maxLength": 2000},
                "evidence_reference": {"type": "string", "minLength": 1, "maxLength": 2000},
                "observation_ids": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "maxItems": 1000},
                "notes": {"type": "string", "maxLength": 2000},
            },
            ["project_root", "kind", "name", "passed", "command", "evidence_reference"],
        ),
    },
    {
        "name": "cleanroom_register_release_candidate",
        "description": "Register and hash the concrete release artifacts that passed validation.",
        "inputSchema": _schema(
            {
                "project_root": {"type": "string"},
                "version": {"type": "string", "minLength": 1, "maxLength": 120},
                "maturity": {"type": "string", "enum": ["alpha", "beta", "stable"]},
                "artifact_paths": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 2000}, "minItems": 1, "maxItems": 100},
                "launch_instructions": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            ["project_root", "version", "maturity", "artifact_paths", "launch_instructions"],
        ),
    },
    {
        "name": "cleanroom_release_gate",
        "description": "Apply the hard completion gate for a verified, validated, packaged working release. Never returns release-ready for partial work.",
        "inputSchema": _schema(
            {"project_root": {"type": "string"}},
            ["project_root"],
        ),
    },
    {
        "name": "cleanroom_status",
        "description": "Report clean-room project state, evidence counts, generated artifacts, and review status.",
        "inputSchema": _schema({"project_root": {"type": "string"}}, ["project_root"]),
    },
    {
        "name": "llm4decompile_status",
        "description": "Check the local LLM4Decompile-compatible PyTorch and Transformers runtime without loading model weights.",
        "inputSchema": _schema({}, []),
    },
    {
        "name": "llm4decompile_refine",
        "description": "Analysis-room only: refine Ghidra pseudocode with an LLM4Decompile V2 model. Never pass reconstructed code into the implementation room.",
        "inputSchema": _schema(
            {
                "ghidra_pseudocode": {"type": "string", "minLength": 1, "maxLength": 100000},
                "model": {"type": "string", "default": "LLM4Binary/llm4decompile-1.3b-v2"},
                "max_new_tokens": {"type": "integer", "minimum": 32, "maximum": 1024, "default": 512},
            },
            ["ghidra_pseudocode"],
        ),
    },
    {
        "name": "llm4decompile_assembly",
        "description": "Analysis-room only: reconstruct C from one assembly function with an LLM4Decompile V1.5 model. Never use the result as implementation source.",
        "inputSchema": _schema(
            {
                "assembly": {"type": "string", "minLength": 1, "maxLength": 100000},
                "model": {"type": "string", "default": "LLM4Binary/llm4decompile-1.3b-v1.5"},
                "max_new_tokens": {"type": "integer", "minimum": 32, "maximum": 1024, "default": 512},
            },
            ["assembly"],
        ),
    },
]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _root(value: str, create: bool = False) -> Path:
    path = Path(value).expanduser().resolve()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise ValueError(f"project_root is not a directory: {path}")
    return path


def _state_root(project_root: str, require_initialized: bool = True) -> tuple[Path, Path]:
    root = _root(project_root)
    state = root / ".cleanroom"
    if require_initialized and not (state / "policy.json").is_file():
        raise ValueError("clean-room project is not initialized")
    return root, state


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _registry_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or tempfile.gettempdir())
    return base / "CleanroomRebuild" / "projects.json"


def _remember_project(root: Path, policy: dict[str, Any]) -> None:
    path = _registry_path()
    registry = _read_json(path, {"schema_version": 1, "projects": []})
    entry = {
        "project_root": str(root),
        "project_name": policy.get("project_name") or root.name,
        "product_goal": policy.get("product_goal") or "",
        "last_opened_at": _now(),
    }
    projects = [item for item in registry.get("projects", []) if item.get("project_root") != str(root)]
    registry["projects"] = [entry] + projects[:19]
    _atomic_json(path, registry)


def _recent_projects() -> list[dict[str, Any]]:
    registry = _read_json(_registry_path(), {"projects": []})
    result = []
    for entry in registry.get("projects", []):
        root_value = entry.get("project_root")
        if not isinstance(root_value, str):
            continue
        root = Path(root_value)
        if (root / ".cleanroom" / "policy.json").is_file():
            result.append(entry)
    return result


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    values = []
    with path.open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    values.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid observation line {number}: {exc}") from exc
    return values


def _looks_like_code(text: str) -> bool:
    lowered = text.lower()
    if "```" in text or text.count(";") >= 3:
        return True
    if text.count("{") + text.count("}") >= 3:
        return True
    code_terms = ("#include", "public static", "private ", "def ", "class ", "return ", "goto ", "while (")
    return sum(term in lowered for term in code_terms) >= 2


def _tokens(code: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(code)]


def _shingles(code: str, size: int) -> set[str]:
    tokens = _tokens(code)
    if len(tokens) < size:
        return set()
    return {
        hashlib.sha256("\x1f".join(tokens[index:index + size]).encode("utf-8")).hexdigest()
        for index in range(len(tokens) - size + 1)
    }


def _clean_list(value: Any, name: str, maximum: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError(f"{name} must be an array of at most 100 strings")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > maximum:
            raise ValueError(f"{name} contains an invalid item")
        if _looks_like_code(item):
            raise ValueError(f"{name} must describe behavior, not contain source-shaped code")
        result.append(item.strip())
    return result


def _initialize(args: dict[str, Any]) -> dict[str, Any]:
    root = _root(args["project_root"], create=True)
    state = root / ".cleanroom"
    for name in ("analysis", "evidence", "handoff", "implementation", "verification"):
        (state / name).mkdir(parents=True, exist_ok=True)
    policy = {
        "schema_version": 1,
        "project_name": args["project_name"].strip(),
        "product_goal": args["product_goal"].strip(),
        "source_description": args["source_description"].strip(),
        "authorization_basis": args["authorization_basis"].strip(),
        "created_at": _now(),
        "rules": {
            "analysis_may_view_reconstructed_code": True,
            "handoff_may_contain_reconstructed_code": False,
            "implementation_must_use_behavior_only_handoff": True,
            "similarity_results_are_not_legal_clearance": True,
        },
    }
    _atomic_json(state / "policy.json", policy)
    _remember_project(root, policy)
    return {"status": "initialized", "project_root": str(root), "state_root": str(state), "policy": policy}


def _record(args: dict[str, Any]) -> dict[str, Any]:
    _, state = _state_root(args["project_root"])
    statement = args["statement"].strip()
    if _looks_like_code(statement):
        raise ValueError("statement appears source-shaped; record observable behavior instead")
    interfaces = _clean_list(args.get("interfaces"), "interfaces", 500)
    tests = _clean_list(args.get("test_vectors"), "test_vectors", 1000)
    identity_material = json.dumps(
        [args["category"], statement, args["source_tool"], args["source_reference"]],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    observation = {
        "id": hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:20],
        "recorded_at": _now(),
        "category": args["category"],
        "statement": statement,
        "confidence": args["confidence"],
        "interfaces": interfaces,
        "test_vectors": tests,
        "provenance": {
            "source_tool": args["source_tool"].strip(),
            "source_reference": args["source_reference"].strip(),
            "source_reference_sha256": hashlib.sha256(args["source_reference"].encode("utf-8")).hexdigest(),
        },
    }
    _append_jsonl(state / "analysis" / "observations.jsonl", observation)
    return {"status": "recorded", "observation_id": observation["id"], "handoff_safe": True}


def _register_fingerprint(args: dict[str, Any]) -> dict[str, Any]:
    _, state = _state_root(args["project_root"])
    size = int(args.get("shingle_size", 7))
    hashes = sorted(_shingles(args["code"], size))
    if not hashes:
        raise ValueError("reference did not contain enough tokens for fingerprinting")
    path = state / "analysis" / "reference_fingerprints.json"
    database = _read_json(path, {"schema_version": 1, "references": []})
    record = {
        "id": hashlib.sha256((args["reference_name"] + "\0" + "".join(hashes)).encode("utf-8")).hexdigest()[:20],
        "name": args["reference_name"].strip(),
        "language": args["language"].strip(),
        "shingle_size": size,
        "token_shingle_count": len(hashes),
        "hashes": hashes,
        "created_at": _now(),
        "raw_code_persisted": False,
    }
    database["references"] = [entry for entry in database.get("references", []) if entry.get("name") != record["name"]]
    database["references"].append(record)
    _atomic_json(path, database)
    return {key: record[key] for key in ("id", "name", "language", "shingle_size", "token_shingle_count", "raw_code_persisted")}


def _handoff(args: dict[str, Any]) -> dict[str, Any]:
    _, state = _state_root(args["project_root"])
    observations = _read_jsonl(state / "analysis" / "observations.jsonl")
    if not observations:
        raise ValueError("no observations have been recorded")
    safe_facts = [
        {
            "id": item["id"],
            "category": item["category"],
            "statement": item["statement"],
            "confidence": item["confidence"],
            "interfaces": item.get("interfaces", []),
            "test_vectors": item.get("test_vectors", []),
        }
        for item in observations
    ]
    policy = _read_json(state / "policy.json", {})
    specification = {
        "schema_version": 1,
        "generated_at": _now(),
        "project_name": policy.get("project_name"),
        "product_goal": policy.get("product_goal"),
        "facts": safe_facts,
        "cleanroom": {
            "contains_source_references": False,
            "contains_reconstructed_source": False,
            "implementation_basis": "observable behavior, interfaces, and tests only",
            "legal_clearance": False,
        },
    }
    handoff_dir = state / "handoff"
    _atomic_json(handoff_dir / "specification.json", specification)
    lines = [
        f"# {specification['project_name']} behavior specification",
        "",
        f"Goal: {specification['product_goal']}",
        "",
        "> Clean-room engineering artifact. This is not legal clearance.",
        "",
    ]
    for category in sorted({fact["category"] for fact in safe_facts}):
        lines.extend([f"## {category.title()}", ""])
        for fact in (entry for entry in safe_facts if entry["category"] == category):
            lines.append(f"- [{fact['confidence']}] {fact['statement']} (`{fact['id']}`)")
            for interface in fact["interfaces"]:
                lines.append(f"  - Interface: {interface}")
            for vector in fact["test_vectors"]:
                lines.append(f"  - Test: {vector}")
        lines.append("")
    (handoff_dir / "specification.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return {"status": "generated", "fact_count": len(safe_facts), "json": str(handoff_dir / "specification.json"), "markdown": str(handoff_dir / "specification.md")}


def _register_feature(args: dict[str, Any]) -> dict[str, Any]:
    _, state = _state_root(args["project_root"])
    known_ids = {item["id"] for item in _read_jsonl(state / "analysis" / "observations.jsonl")}
    observation_ids = args["observation_ids"]
    unknown = sorted(set(observation_ids) - known_ids)
    if unknown:
        raise ValueError(f"unknown observation IDs: {', '.join(unknown[:20])}")
    path = state / "analysis" / "feature-inventory.json"
    inventory = _read_json(path, {"schema_version": 1, "features": []})
    feature = {
        "feature_id": args["feature_id"],
        "name": args["name"].strip(),
        "kind": args["kind"],
        "status": args["status"],
        "observation_ids": sorted(set(observation_ids)),
        "evidence_reference": args["evidence_reference"].strip(),
        "updated_at": _now(),
    }
    inventory["features"] = [entry for entry in inventory.get("features", []) if entry.get("feature_id") != feature["feature_id"]]
    inventory["features"].append(feature)
    inventory["features"].sort(key=lambda entry: entry["feature_id"])
    _atomic_json(path, inventory)
    return {"status": "registered", "feature_id": feature["feature_id"], "feature_status": feature["status"], "observation_count": len(feature["observation_ids"])}


def _plan(args: dict[str, Any]) -> dict[str, Any]:
    _, state = _state_root(args["project_root"])
    specification = _read_json(state / "handoff" / "specification.json", None)
    if specification is None:
        raise ValueError("generate the behavior-only handoff first")
    constraints = _clean_list(args.get("constraints"), "constraints", 500)
    priorities = _clean_list(args.get("priorities"), "priorities", 500)
    interfaces = sorted({value for fact in specification["facts"] for value in fact.get("interfaces", [])})
    categories = sorted({fact["category"] for fact in specification["facts"]})
    phases = [
        {"id": "contract-tests", "goal": "Turn every handoff fact and test vector into executable black-box acceptance tests.", "depends_on": []},
        {"id": "interface-shell", "goal": "Implement public interfaces and formats with independent naming and structure.", "depends_on": ["contract-tests"]},
        {"id": "minimal-core", "goal": "Implement the smallest independent core that satisfies the highest-value behavior.", "depends_on": ["interface-shell"]},
        {"id": "compatibility", "goal": "Close compatibility, error, state, and persistence gaps using black-box tests.", "depends_on": ["minimal-core"]},
        {"id": "efficiency", "goal": "Measure and optimize latency, throughput, memory, and token cost without importing reference expression.", "depends_on": ["compatibility"]},
        {"id": "separation-review", "goal": "Run provenance and hashed-shingle similarity review, then obtain human/legal release review.", "depends_on": ["efficiency"]},
    ]
    plan = {
        "schema_version": 1,
        "generated_at": _now(),
        "project_name": specification.get("project_name"),
        "priorities": priorities,
        "constraints": constraints,
        "interfaces": interfaces,
        "behavior_categories": categories,
        "phases": phases,
        "parallelization": {
            "safe_parallel_work": ["independent interface adapters", "independent black-box test families", "documentation and provenance review"],
            "serialization_points": ["handoff freeze", "public contract approval", "final separation review"],
        },
    }
    path = state / "implementation" / "plan.json"
    _atomic_json(path, plan)
    return {"status": "planned", "path": str(path), "phase_count": len(phases), "interface_count": len(interfaces)}


def _contained_path(root: Path, value: str) -> Path:
    path = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("implementation_path must remain inside project_root") from exc
    return path


def _source_files(path: Path) -> Iterable[Path]:
    if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS:
        yield path
        return
    if not path.is_dir():
        return
    for file in path.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if any(part in {".git", ".cleanroom", "node_modules", ".venv", "dist", "build"} for part in file.parts):
            continue
        yield file


def _similarity(args: dict[str, Any]) -> dict[str, Any]:
    root, state = _state_root(args["project_root"])
    database = _read_json(state / "analysis" / "reference_fingerprints.json", {"references": []})
    references = database.get("references", [])
    if not references:
        raise ValueError("no hashed reference fingerprints are registered")
    implementation = _contained_path(root, args.get("implementation_path", ".cleanroom/implementation"))
    threshold = float(args.get("review_threshold", 0.08))
    results = []
    for file in _source_files(implementation):
        text = file.read_text(encoding="utf-8", errors="ignore")
        comparisons = []
        for reference in references:
            implementation_hashes = _shingles(text, int(reference["shingle_size"]))
            reference_hashes = set(reference["hashes"])
            overlap = len(implementation_hashes & reference_hashes)
            ratio = overlap / max(1, len(implementation_hashes))
            comparisons.append({"reference": reference["name"], "overlap_shingles": overlap, "implementation_ratio": round(ratio, 6)})
        worst = max(comparisons, key=lambda item: item["implementation_ratio"])
        results.append({"file": str(file.relative_to(root)), "worst": worst, "review_required": worst["implementation_ratio"] >= threshold})
    report = {
        "schema_version": 1,
        "generated_at": _now(),
        "threshold": threshold,
        "legal_clearance": False,
        "files_checked": len(results),
        "review_required": any(item["review_required"] for item in results),
        "results": sorted(results, key=lambda item: item["worst"]["implementation_ratio"], reverse=True),
        "limitations": ["Token-shingle overlap can produce false positives and false negatives.", "A low score does not prove non-infringement or clean-room compliance."],
    }
    path = state / "verification" / "similarity-report.json"
    _atomic_json(path, report)
    return {"status": "checked", "report": str(path), **{key: report[key] for key in ("files_checked", "review_required", "threshold", "legal_clearance")}}


def _record_validation(args: dict[str, Any]) -> dict[str, Any]:
    _, state = _state_root(args["project_root"])
    known_ids = {item["id"] for item in _read_jsonl(state / "analysis" / "observations.jsonl")}
    observation_ids = args.get("observation_ids") or []
    if not isinstance(observation_ids, list) or len(observation_ids) > 1000:
        raise ValueError("observation_ids must be an array of at most 1000 IDs")
    unknown = sorted(set(observation_ids) - known_ids)
    if unknown:
        raise ValueError(f"unknown observation IDs: {', '.join(unknown[:20])}")
    evidence_reference = args["evidence_reference"].strip()
    record = {
        "id": hashlib.sha256((args["kind"] + "\0" + args["name"] + "\0" + evidence_reference + "\0" + _now()).encode("utf-8")).hexdigest()[:20],
        "recorded_at": _now(),
        "kind": args["kind"],
        "name": args["name"].strip(),
        "passed": bool(args["passed"]),
        "command": args["command"].strip(),
        "evidence_reference": evidence_reference,
        "evidence_sha256": hashlib.sha256(evidence_reference.encode("utf-8")).hexdigest(),
        "observation_ids": sorted(set(observation_ids)),
        "notes": (args.get("notes") or "").strip(),
    }
    _append_jsonl(state / "verification" / "validations.jsonl", record)
    return {"status": "recorded", "validation_id": record["id"], "kind": record["kind"], "passed": record["passed"], "coverage_count": len(record["observation_ids"])}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact_record(root: Path, value: str) -> dict[str, Any]:
    path = _contained_path(root, value)
    if not path.exists():
        raise ValueError(f"release artifact does not exist: {path}")
    if path.is_file():
        return {"path": str(path.relative_to(root)), "type": "file", "size": path.stat().st_size, "sha256": _hash_file(path)}
    if not path.is_dir():
        raise ValueError(f"unsupported release artifact type: {path}")
    members = []
    total_size = 0
    for file in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = file.relative_to(path).as_posix()
        size = file.stat().st_size
        total_size += size
        members.append({"path": relative, "size": size, "sha256": _hash_file(file)})
    manifest_bytes = json.dumps(members, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"path": str(path.relative_to(root)), "type": "directory", "size": total_size, "file_count": len(members), "sha256": hashlib.sha256(manifest_bytes).hexdigest()}


def _register_release(args: dict[str, Any]) -> dict[str, Any]:
    root, state = _state_root(args["project_root"])
    artifact_paths = args["artifact_paths"]
    if not isinstance(artifact_paths, list) or not artifact_paths or len(artifact_paths) > 100:
        raise ValueError("artifact_paths must contain 1 to 100 paths")
    artifacts = [_artifact_record(root, value) for value in artifact_paths]
    candidate = {
        "schema_version": 1,
        "registered_at": _now(),
        "version": args["version"].strip(),
        "maturity": args["maturity"],
        "launch_instructions": args["launch_instructions"].strip(),
        "artifacts": artifacts,
        "legal_clearance": False,
    }
    path = state / "verification" / "release-candidate.json"
    _atomic_json(path, candidate)
    return {"status": "registered", "version": candidate["version"], "maturity": candidate["maturity"], "artifact_count": len(artifacts), "manifest": str(path), "artifacts": artifacts}


def _release_gate(args: dict[str, Any]) -> dict[str, Any]:
    _, state = _state_root(args["project_root"])
    observations = _read_jsonl(state / "analysis" / "observations.jsonl")
    validations = _read_jsonl(state / "verification" / "validations.jsonl")
    similarity = _read_json(state / "verification" / "similarity-report.json", None)
    candidate = _read_json(state / "verification" / "release-candidate.json", None)
    inventory = _read_json(state / "analysis" / "feature-inventory.json", {"features": []})
    features = inventory.get("features", [])
    required_kinds = {"build", "unit", "integration", "compatibility", "regression", "smoke", "packaging", "security", "performance"}
    passed = [item for item in validations if item.get("passed") is True]
    failed = [item for item in validations if item.get("passed") is False]
    passed_kinds = {item.get("kind") for item in passed}
    required_observations = {item["id"] for item in observations if item.get("category") != "uncertainty"}
    covered = {observation_id for item in passed if item.get("kind") in {"compatibility", "integration", "regression", "smoke"} for observation_id in item.get("observation_ids", [])}
    blockers = []
    if not observations:
        blockers.append("No behavioral observations were recorded.")
    if not (state / "handoff" / "specification.json").is_file():
        blockers.append("Behavior-only handoff is missing.")
    if not (state / "implementation" / "plan.json").is_file():
        blockers.append("Implementation plan is missing.")
    missing_kinds = sorted(required_kinds - passed_kinds)
    if missing_kinds:
        blockers.append("Missing passing validation kinds: " + ", ".join(missing_kinds))
    if failed:
        blockers.append(f"{len(failed)} recorded validation(s) are failing.")
    uncovered = sorted(required_observations - covered)
    if uncovered:
        blockers.append(f"{len(uncovered)} behavioral observation(s) lack passing compatibility coverage.")
    if candidate is None or not candidate.get("artifacts"):
        blockers.append("A hashed release candidate is not registered.")
    elif candidate.get("maturity") not in {"beta", "stable"}:
        blockers.append("Release candidate maturity is below Beta.")
    if not features:
        blockers.append("Feature, capability, and workflow inventory is empty.")
    else:
        incomplete_features = [item["feature_id"] for item in features if item.get("status") != "verified"]
        if incomplete_features:
            blockers.append(f"{len(incomplete_features)} inventory item(s) are not verified.")
        feature_observations = {observation_id for item in features for observation_id in item.get("observation_ids", [])}
        missing_inventory_coverage = sorted(required_observations - feature_observations)
        if missing_inventory_coverage:
            blockers.append(f"{len(missing_inventory_coverage)} behavioral observation(s) are not mapped to the feature inventory.")
    if similarity is None:
        blockers.append("Similarity/separation review is missing.")
    elif similarity.get("review_required"):
        blockers.append("Similarity/separation review has unresolved flags.")
    release_ready = not blockers
    gate = {
        "schema_version": 1,
        "evaluated_at": _now(),
        "release_ready": release_ready,
        "verified": release_ready,
        "validated": release_ready,
        "working_release_registered": candidate is not None and bool(candidate.get("artifacts")),
        "behavior_observations": len(observations),
        "covered_observations": len(required_observations & covered),
        "validation_count": len(validations),
        "inventory_items": len(features),
        "verified_inventory_items": sum(1 for item in features if item.get("status") == "verified"),
        "passed_validation_kinds": sorted(passed_kinds),
        "blockers": blockers,
        "legal_clearance": False,
        "legal_note": "Engineering verification does not determine copyright, license, patent, contract, trade-secret, or anti-circumvention compliance.",
    }
    _atomic_json(state / "verification" / "release-gate.json", gate)
    return gate


def _status(args: dict[str, Any]) -> dict[str, Any]:
    _, state = _state_root(args["project_root"])
    observations = _read_jsonl(state / "analysis" / "observations.jsonl")
    fingerprints = _read_json(state / "analysis" / "reference_fingerprints.json", {"references": []})
    report = _read_json(state / "verification" / "similarity-report.json", None)
    gate = _read_json(state / "verification" / "release-gate.json", None)
    inventory = _read_json(state / "analysis" / "feature-inventory.json", {"features": []})
    return {
        "initialized": True,
        "observation_count": len(observations),
        "fingerprint_count": len(fingerprints.get("references", [])),
        "feature_inventory_count": len(inventory.get("features", [])),
        "verified_feature_count": sum(1 for item in inventory.get("features", []) if item.get("status") == "verified"),
        "handoff_generated": (state / "handoff" / "specification.json").is_file(),
        "implementation_planned": (state / "implementation" / "plan.json").is_file(),
        "similarity_review": None if report is None else {"generated_at": report.get("generated_at"), "review_required": report.get("review_required"), "files_checked": report.get("files_checked")},
        "release_ready": False if gate is None else bool(gate.get("release_ready")),
        "release_blockers": [] if gate is None else gate.get("blockers", []),
    }


def _dashboard(args: dict[str, Any]) -> dict[str, Any]:
    projects = _recent_projects()
    requested = (args.get("project_root") or "").strip()
    if requested:
        root = _root(requested)
        state = root / ".cleanroom"
        if not (state / "policy.json").is_file():
            raise ValueError("selected directory is not an initialized clean-room project")
        policy = _read_json(state / "policy.json", {})
        _remember_project(root, policy)
        projects = _recent_projects()
    elif projects:
        root = Path(projects[0]["project_root"])
        state = root / ".cleanroom"
        policy = _read_json(state / "policy.json", {})
    else:
        return {
            "configured": False,
            "no_llm_used": True,
            "message": "No clean-room projects have been initialized yet.",
            "projects": [],
            "refreshed_at": _now(),
        }

    observations = _read_jsonl(state / "analysis" / "observations.jsonl")
    validations = _read_jsonl(state / "verification" / "validations.jsonl")
    inventory = _read_json(state / "analysis" / "feature-inventory.json", {"features": []}).get("features", [])
    similarity = _read_json(state / "verification" / "similarity-report.json", None)
    candidate = _read_json(state / "verification" / "release-candidate.json", None)
    gate = _read_json(state / "verification" / "release-gate.json", None)
    fingerprints = _read_json(state / "analysis" / "reference_fingerprints.json", {"references": []}).get("references", [])
    handoff_ready = (state / "handoff" / "specification.json").is_file()
    plan_ready = (state / "implementation" / "plan.json").is_file()
    implementation_files = list(_source_files(state / "implementation"))
    required_kinds = ["build", "unit", "integration", "compatibility", "regression", "smoke", "packaging", "security", "performance"]
    latest_by_kind: dict[str, dict[str, Any]] = {}
    for record in validations:
        latest_by_kind[record.get("kind", "unknown")] = record
    validation_matrix = [
        {
            "kind": kind,
            "status": "passed" if latest_by_kind.get(kind, {}).get("passed") is True else "failed" if latest_by_kind.get(kind, {}).get("passed") is False else "pending",
            "name": latest_by_kind.get(kind, {}).get("name"),
            "recorded_at": latest_by_kind.get(kind, {}).get("recorded_at"),
            "evidence_reference": latest_by_kind.get(kind, {}).get("evidence_reference"),
        }
        for kind in required_kinds
    ]
    passed_kinds = {item["kind"] for item in validation_matrix if item["status"] == "passed"}
    required_observations = {item["id"] for item in observations if item.get("category") != "uncertainty"}
    covered_observations = {
        observation_id
        for item in validations
        if item.get("passed") is True and item.get("kind") in {"compatibility", "integration", "regression", "smoke"}
        for observation_id in item.get("observation_ids", [])
    }
    verified_features = [item for item in inventory if item.get("status") == "verified"]
    feature_observations = {observation_id for item in inventory for observation_id in item.get("observation_ids", [])}

    milestones = [
        ("initialize", "Initialize authorized project", True),
        ("analyze", "Analyze observable behavior", bool(observations)),
        ("inventory", "Inventory features and workflows", bool(inventory)),
        ("handoff", "Freeze behavior-only handoff", handoff_ready),
        ("plan", "Plan independent implementation", plan_ready),
        ("implement", "Implement independent product", bool(implementation_files) or candidate is not None),
        ("validate", "Run nine validation classes", len(passed_kinds) == len(required_kinds)),
        ("separation", "Complete similarity review", similarity is not None and similarity.get("review_required") is False),
        ("package", "Package Beta-or-better candidate", candidate is not None and candidate.get("maturity") in {"beta", "stable"}),
        ("release", "Pass hard release gate", gate is not None and gate.get("release_ready") is True),
    ]
    first_pending = next((index for index, item in enumerate(milestones) if not item[2]), len(milestones))
    steps = []
    for index, (step_id, label, complete) in enumerate(milestones):
        status = "complete" if complete else "active" if index == first_pending else "pending"
        steps.append({"id": step_id, "label": label, "status": status})

    blockers = []
    if not observations:
        blockers.append("No behavioral observations recorded.")
    if not inventory:
        blockers.append("Feature, capability, and workflow inventory is empty.")
    elif len(verified_features) != len(inventory):
        blockers.append(f"{len(inventory) - len(verified_features)} inventory item(s) are not verified.")
    if required_observations - feature_observations:
        blockers.append(f"{len(required_observations - feature_observations)} observation(s) are not mapped to inventory items.")
    if not handoff_ready:
        blockers.append("Behavior-only handoff is missing.")
    if not plan_ready:
        blockers.append("Implementation plan is missing.")
    missing_validations = [kind for kind in required_kinds if kind not in passed_kinds]
    if missing_validations:
        blockers.append("Missing passing validations: " + ", ".join(missing_validations) + ".")
    if required_observations - covered_observations:
        blockers.append(f"{len(required_observations - covered_observations)} observation(s) lack compatibility coverage.")
    if similarity is None:
        blockers.append("Similarity review is missing.")
    elif similarity.get("review_required"):
        blockers.append("Similarity review has unresolved flags.")
    if candidate is None:
        blockers.append("No release candidate is registered.")
    elif candidate.get("maturity") not in {"beta", "stable"}:
        blockers.append("Release candidate maturity is below Beta.")

    activity = []
    for item in observations[-12:]:
        activity.append({"time": item.get("recorded_at"), "type": "observation", "label": item.get("statement"), "status": item.get("confidence")})
    for item in validations[-12:]:
        activity.append({"time": item.get("recorded_at"), "type": "validation", "label": f"{item.get('kind')}: {item.get('name')}", "status": "passed" if item.get("passed") else "failed"})
    activity.sort(key=lambda item: item.get("time") or "", reverse=True)

    return {
        "configured": True,
        "no_llm_used": True,
        "data_source": "direct local workflow state",
        "refreshed_at": _now(),
        "project": {
            "root": str(root),
            "name": policy.get("project_name") or root.name,
            "goal": policy.get("product_goal") or "",
            "authorization_basis": policy.get("authorization_basis") or "",
        },
        "projects": projects,
        "progress": {
            "percent": round(sum(1 for item in milestones if item[2]) / len(milestones) * 100),
            "completed_steps": sum(1 for item in milestones if item[2]),
            "total_steps": len(milestones),
            "steps": steps,
        },
        "counts": {
            "observations": len(observations),
            "reference_fingerprints": len(fingerprints),
            "inventory_items": len(inventory),
            "verified_inventory_items": len(verified_features),
            "covered_observations": len(required_observations & covered_observations),
            "required_observations": len(required_observations),
            "implementation_files": len(implementation_files),
            "validations": len(validations),
            "passing_validation_kinds": len(passed_kinds),
        },
        "inventory": inventory,
        "validations": validation_matrix,
        "similarity": similarity,
        "release_candidate": candidate,
        "release_gate": gate,
        "release_ready": gate is not None and gate.get("release_ready") is True,
        "blockers": [] if gate is not None and gate.get("release_ready") is True else blockers,
        "recent_activity": activity[:20],
        "runtime": _llm_status({}),
    }


def _llm_status(_: dict[str, Any]) -> dict[str, Any]:
    try:
        import torch
        import transformers
        accelerators = _gpu_backends(torch)
        priority = _backend_order(torch)
        return {
            "available": True,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "accelerators": accelerators,
            "backend_priority": [f"{item['kind']}:{item['index']}" if item["index"] is not None else "cpu" for item in priority],
            "gpu_first": bool(accelerators),
            "cpu_fallback": True,
            "cuda_cpu_offload": any(item["kind"] == "cuda" for item in accelerators),
            "cached_models": {name: values[2] for name, values in MODEL_CACHE.items()},
        }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _gpu_backends(torch: Any) -> list[dict[str, Any]]:
    backends: list[dict[str, Any]] = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            free, total = torch.cuda.mem_get_info(index)
            backends.append({"kind": "cuda", "index": index, "name": torch.cuda.get_device_name(index), "free_bytes": free, "total_bytes": total})
    xpu = getattr(torch, "xpu", None)
    if xpu is not None and xpu.is_available():
        for index in range(xpu.device_count()):
            backends.append({"kind": "xpu", "index": index, "name": xpu.get_device_name(index)})
    try:
        import torch_directml
        for index in range(torch_directml.device_count()):
            backends.append({"kind": "directml", "index": index, "name": torch_directml.device_name(index).rstrip("\0")})
    except Exception:
        pass
    return backends


def _backend_order(torch: Any) -> list[dict[str, Any]]:
    requested = os.environ.get("LLM4DECOMPILE_DEVICE", "auto").strip().lower()
    configured_index = os.environ.get("LLM4DECOMPILE_GPU_INDEX")
    candidates = _gpu_backends(torch)
    if configured_index is not None:
        try:
            preferred_index = int(configured_index)
        except ValueError as exc:
            raise ValueError("LLM4DECOMPILE_GPU_INDEX must be an integer") from exc
        candidates.sort(key=lambda item: item["index"] != preferred_index)
    cuda = sorted((item for item in candidates if item["kind"] == "cuda"), key=lambda item: item.get("free_bytes", 0), reverse=True)
    xpu = [item for item in candidates if item["kind"] == "xpu"]
    directml = [item for item in candidates if item["kind"] == "directml"]
    ordered = cuda + xpu + directml
    cpu = {"kind": "cpu", "index": None, "name": "CPU"}
    if requested == "cpu":
        return [cpu]
    if requested != "auto":
        kind, _, suffix = requested.partition(":")
        selected = [item for item in ordered if item["kind"] == kind and (not suffix or item["index"] == int(suffix))]
        if not selected:
            raise RuntimeError(f"requested accelerator is unavailable: {requested}")
        return selected + [cpu]
    return ordered + [cpu]


def _load_model(model_name: str) -> tuple[Any, Any, str, Any]:
    if model_name in MODEL_CACHE:
        return MODEL_CACHE[model_name]
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    failures = []
    for backend in _backend_order(torch):
        kind = backend["kind"]
        try:
            kwargs: dict[str, Any] = {"low_cpu_mem_usage": True}
            if kind == "cuda":
                kwargs["device_map"] = "auto"
                kwargs["torch_dtype"] = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
                model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)
                input_device = model.device
                label = f"cuda:{backend['index']} + cpu-offload"
            elif kind == "xpu":
                device = torch.device(f"xpu:{backend['index']}")
                model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs).to(device)
                input_device = device
                label = f"xpu:{backend['index']}"
            elif kind == "directml":
                import torch_directml
                device = torch_directml.device(backend["index"])
                model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs).to(device)
                input_device = device
                label = f"directml:{backend['index']} ({backend['name']})"
            else:
                device = torch.device("cpu")
                model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs).to(device)
                input_device = device
                label = "cpu"
            model.eval()
            MODEL_CACHE[model_name] = (tokenizer, model, label, input_device)
            return MODEL_CACHE[model_name]
        except Exception as exc:
            failures.append(f"{kind}:{backend.get('index')}: {type(exc).__name__}: {exc}")
    raise RuntimeError("all model backends failed: " + " | ".join(failures))


def _generate(prompt: str, model_name: str, max_new_tokens: int) -> dict[str, Any]:
    import torch
    tokenizer, model, device, input_device = _load_model(model_name)
    inputs = tokenizer(prompt, return_tensors="pt").to(input_device)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    generated = outputs[0][inputs["input_ids"].shape[1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    return {"model": model_name, "device": device, "reconstruction": text, "cleanroom_usage": "analysis-room only; convert only observable behavior into the handoff"}


def _llm_refine(args: dict[str, Any]) -> dict[str, Any]:
    prompt = "# This is the decompiled code:\n" + args["ghidra_pseudocode"].strip() + "\n# What is the source code?\n"
    return _generate(prompt, args.get("model", "LLM4Binary/llm4decompile-1.3b-v2"), int(args.get("max_new_tokens", 512)))


def _llm_assembly(args: dict[str, Any]) -> dict[str, Any]:
    prompt = "# This is the assembly code:\n" + args["assembly"].strip() + "\n# What is the source code?\n"
    return _generate(prompt, args.get("model", "LLM4Binary/llm4decompile-1.3b-v1.5"), int(args.get("max_new_tokens", 512)))


HANDLERS = {
    "cleanroom_dashboard": _dashboard,
    "cleanroom_initialize": _initialize,
    "cleanroom_record_observation": _record,
    "cleanroom_register_reference_fingerprint": _register_fingerprint,
    "cleanroom_generate_handoff": _handoff,
    "cleanroom_register_feature": _register_feature,
    "cleanroom_plan_implementation": _plan,
    "cleanroom_check_similarity": _similarity,
    "cleanroom_record_validation": _record_validation,
    "cleanroom_register_release_candidate": _register_release,
    "cleanroom_release_gate": _release_gate,
    "cleanroom_status": _status,
    "llm4decompile_status": _llm_status,
    "llm4decompile_refine": _llm_refine,
    "llm4decompile_assembly": _llm_assembly,
}


def _result(request_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_result(value: Any, is_error: bool = False) -> dict[str, Any]:
    text = json.dumps(value, indent=2, ensure_ascii=False)
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if isinstance(value, dict):
        result["structuredContent"] = value
    if is_error:
        result["isError"] = True
    return result


def _handle(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        requested = params.get("protocolVersion", "2024-11-05")
        return _result(request_id, {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "resources/list":
        return _result(request_id, {"resources": [{"uri": STATUS_RESOURCE_URI, "name": "Clean-room live status", "title": "Clean-room Live Status", "description": "Zero-LLM live workflow dashboard", "mimeType": "text/html;profile=mcp-app"}]})
    if method == "resources/read":
        uri = params.get("uri")
        if uri != STATUS_RESOURCE_URI:
            return _error(request_id, -32002, f"resource not found: {uri}")
        dashboard_path = Path(__file__).resolve().parent.parent / "ui" / "status-dashboard.html"
        if not dashboard_path.is_file():
            return _error(request_id, -32603, "status dashboard asset is missing")
        return _result(request_id, {"contents": [{
            "uri": STATUS_RESOURCE_URI,
            "mimeType": "text/html;profile=mcp-app",
            "text": dashboard_path.read_text(encoding="utf-8"),
            "_meta": {
                "ui": {"prefersBorder": False, "csp": {"connectDomains": [], "resourceDomains": []}},
                "openai/ui": {"availableDisplayModes": ["inline", "fullscreen", "pip"]},
            },
        }]})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if handler is None:
            return _result(request_id, _tool_result({"error": f"unknown tool: {name}"}, True))
        try:
            return _result(request_id, _tool_result(handler(arguments)))
        except Exception as exc:
            return _result(request_id, _tool_result({"error": f"{type(exc).__name__}: {exc}"}, True))
    return _error(request_id, -32601, f"method not found: {method}")


def _messages() -> Iterable[dict[str, Any]]:
    stream = sys.stdin.buffer
    while True:
        line = stream.readline()
        if not line:
            return
        if not line.strip():
            continue
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
            while True:
                header = stream.readline()
                if header in (b"\r\n", b"\n", b""):
                    break
            payload = stream.read(length)
        else:
            payload = line.strip()
        yield json.loads(payload.decode("utf-8"))


def main() -> None:
    for message in _messages():
        try:
            response = _handle(message)
        except Exception as exc:
            response = _error(message.get("id"), -32603, f"internal error: {type(exc).__name__}: {exc}")
        if response is not None:
            payload = (json.dumps(response, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
