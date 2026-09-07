"""Typed observation comparison for browser, database, and integration adapters."""
import json
from decimal import Decimal

from .discovery import digest
from .engine import check, encode
from .runner import create_job, execute_job


def strict_json(raw):
    def pairs(items):
        d = {}
        for k, v in items:
            check(k not in d, f"Duplicate observation key: {k}")
            d[k] = v
        return d
    def constant(value):
        raise ValueError(f"Nonfinite JSON number: {value}")
    return json.loads(raw, parse_float=Decimal, parse_constant=constant, object_pairs_hook=pairs)


def typed(value):
    if value is None: return ["null"]
    if type(value) is bool: return ["boolean", value]
    if type(value) is int: return ["integer", str(value)]
    if isinstance(value, Decimal): return ["decimal", str(value)]
    if type(value) is str: return ["string", value]
    if type(value) is list: return ["array", [typed(v) for v in value]]
    if type(value) is dict: return ["object", [[k, typed(v)] for k, v in sorted(value.items())]]
    raise ValueError("Unsupported observation type")


def decode_observation(raw, dimension):
    value = strict_json(raw)
    check(isinstance(value, dict) and value.get("schema_version") == 1 and value.get("dimension") == dimension,
          "Adapter must return schema_version=1 and the declared dimension")
    check(set(value) == {"schema_version", "dimension", "observations"}, "Unexpected observation envelope fields")
    obs = value["observations"]
    check(isinstance(obs, dict) and obs, "Empty observations cannot establish parity")
    canonical = typed(obs)
    return canonical, digest(encode(canonical).encode())


def compare_capture(engine, scenario):
    evidence = {"dimension": scenario["dimension"], "jobs": {}}
    outputs = {}
    for side in ["legacy", "target"]:
        id = create_job(engine, scenario[side + "_command"])
        result = execute_job(engine, id)
        evidence["jobs"][side] = result
        if result["state"] != "passed":
            return "blocked", {**evidence, "differences": [side + "_capture_not_passed"]}
        raw = (engine.state / "jobs" / id / "stdout.bin").read_bytes()
        outputs[side], sha = decode_observation(raw, scenario["dimension"])
        evidence[side + "_sha256"] = sha
    if evidence["legacy_sha256"] != scenario["legacy_observation_sha256"]:
        return "blocked", {**evidence, "differences": ["legacy_observation_changed_from_characterized_fixture"]}
    equal = outputs["legacy"] == outputs["target"]
    # Digest uses typed values, so booleans, integers, decimals, and strings cannot compare equal by coercion.
    evidence["differences"] = [] if equal else ["typed_observations_differ"]
    if not equal:
        old, new = dict(outputs["legacy"][1]), dict(outputs["target"][1])
        evidence["different_observation_keys"] = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
    return "passed" if equal else "failed", evidence
