"""Register the reference example, leaving runtime confirmation explicitly blocked."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modernizer.engine import Engine
from modernizer.observations import decode_observation

manifest = Path(__file__).parent / "control/migration.json"
with Engine(manifest) as e:
    if e.records("feature"):
        raise SystemExit("Example ledger already has features; retain it and continue, rather than overwrite decisions.")
    source = [{"root":"legacy","path":p} for p in ["Program.cs","Pages/Index.cshtml","Legacy.csproj"]]
    target = [{"root":"java","path":"InvoiceServer.java"},
              *[{"root":"react","path":p} for p in ["src/main.jsx","package.json","vite.config.js","index.html"]]]
    e.put("feature", {"id":"Invoice","title":"Reference invoice screen and API",
        "contract":"Reference scenario scope: GET invoice 42 preserves exact amount text; missing ID preserves legacy typo. Browser form uses same text and request. Other request forms are unverified.",
        "source_refs":source,"target_refs":target,"depends_on":[],
        "required_scenarios":["InvoiceOK","MissingID","UnknownID","BrowserMissingID"],"required_dimensions":["http","ui"]})
    cases = [("InvoiceOK","/api/invoice?id=42",200,'{"id":"42","amount":"9007199254740993.10"}'),
             ("MissingID","/api/invoice?id=",400,'{"error":"Id requried!"}'),
             ("UnknownID","/api/invoice?id=99",404,'{"error":"Not found"}')]
    for id,path,status,body in cases:
        e.put("scenario", {"id":id,"feature_id":"Invoice","path":path,"legacy_status":status,
            "legacy_body_sha256":hashlib.sha256(body.encode()).hexdigest(),"compare_headers":["content-type"]})
    envelope = {"schema_version":1,"dimension":"ui","observations":{"error":"Id requried!","amount":"","input":"","path":"/"}}
    _, sha = decode_observation(json.dumps(envelope), "ui")
    e.put("scenario", {"id":"BrowserMissingID","feature_id":"Invoice","adapter":"observation","dimension":"ui",
        "legacy_command":"browser-legacy","target_command":"browser-target","legacy_observation_sha256":sha})
    e.put("type_mapping", {"id":"InvoiceDecimal","feature_ids":["Invoice"],"source_type":"C# decimal F2 invariant string",
        "target_type":"Java BigDecimal toPlainString; React string",
        "semantics":"For the fixed sample value, preserve 9007199254740993.10 without browser Number conversion. General arithmetic/rounding is outside this sample.",
        "scenario_ids":["InvoiceOK"],"source_refs":[source[0]]})
    e.put("defect", {"id":"LegacyTypo","feature_id":"Invoice","description":"Preserve the misspelled Id requried! error. Any fix is a separate proposed change.",
        "source_refs":[source[0]],"scenario_ids":["MissingID","BrowserMissingID"]})
    e.put("plan", {"id":"InvoicePlan","feature_id":"Invoice","architecture":"Reference example only: .NET 8/Razor to Java HttpServer and React/Vite. Not a framework decision for the user's applications.",
        "type_mapping_ids":["InvoiceDecimal"],"required_commands":["build-csharp","build-java","build-react"],"implementation_roles":["backend","ui"],"confirmed_by":"Explicit bundled reference-example design"})
    e.scan()
    for i,ref in enumerate(source):
        e.put("disposition", {"id":"Source"+str(i),"source_ref":ref,"source_sha256":hashlib.sha256(e.resolve_ref(ref).read_bytes()).hexdigest(),
            "disposition":"feature","feature_ids":["Invoice"],"reason":"Bundled example source for the single registered feature","reviewed_by":"Reference example author; not a user-app review"})
    e.put("question", {"id":"RuntimeBaseline","question":"Build and run the reference systems and confirm the characterized legacy API/browser outputs. Replace declared build IDs with actual build identities before verification.",
        "feature_ids":["Invoice"],"blocking":True,"answer":None})
    e.map()
    print(json.dumps(e.next_action(), indent=2))
