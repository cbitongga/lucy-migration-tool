# Legacy Upgrade Companion for You L-U-C-Y

**Understand the past. Build the next. Verify the match.**

An evidence-led C#/.NET to Java/React migration workflow for **Copilot and Claude
Code**, with native specialist agents, a durable Python engine, optional MCP,
and executable comparison adapters.

**This release is a working orchestration system, not a guarantee of complete
migration for arbitrary applications.** Agents perform analysis and code changes
inside your coding client. Engine checks measure declared behavior. Missing
runtime evidence remains a blocker; no model is allowed to certify perfection.

## Start here

1. Extract the package and open the tool folder alongside your application roots.
2. Register roots and inspect prerequisites. Keep the control directory outside
   the source/target application roots:

   ```sh
   python3 run_modernizer.py --manifest /path/control/migration.json init --source /path/legacy --target /path/target
   python3 run_modernizer.py --manifest /path/control/migration.json doctor
   ```

3. Configure your client, using the SAME manifest for either agent:

   ```sh
   python3 run_modernizer.py --manifest /path/control/migration.json claude-config --output .mcp.json
   ```

   For Copilot use `vscode-config` and merge its server entry into your VS Code
   MCP configuration. Output is JSON unless `--output` is provided. Existing
   unrelated entries are retained; conflicting server registrations are rejected.

4. In Claude Code, launch the main coordinator:

   ```sh
   claude --agent migration-coordinator --add-dir /path/legacy --add-dir /path/target --add-dir /path/control
   ```

   In Copilot select `migration-coordinator` from custom agents. The coordinator
   delegates to discovery, planning, backend, UI, verification and review agents.
   Inspect the client's agent/tool list if organization policy limits discovery.

5. Ask the coordinator to continue the migration using `migration_next_action`.
   It inspects durable state, delegates the next bounded task, and checks saved
   evidence before moving on. Run one writing session per workspace at a time.

The seven role definitions are supplied in both `.claude/agents` and
`.github/agents`. If your client discovers both formats, use one matching set in
its project to avoid duplicate menu entries. `agents-install --destination PATH`
can copy the definitions to another project; it rejects conflicting files.
Preserve your project's own instructions when merging the shared guidance.

## What changed in 0.2

| Area | Implemented |
| --- | --- |
| Application map | Source/target files, project dependencies, types, method/route candidates, type uses, data/exception points, reviewed feature links; JSON/Mermaid export |
| Semantic evidence | Optional Roslyn adapter source and hash-checked import of successful adapter jobs; unresolved bindings/diagnostics remain visible |
| Specialist agents | Coordinator plus six native client roles, generated from one canonical role catalog |
| Workflow | Next eligible action from questions, file accounting, plans, type maps, role outputs, implementation state, builds, comparisons and review |
| Build/test execution | Explicit manifest argv commands, durable background jobs, output limits, deadlines, exit status and stale-input checks |
| Parity adapters | Existing HTTP checks; typed observation comparison; read-only SQLite snapshots; Playwright browser actions/observations |
| Coverage | Current source-file dispositions, per-dimension scenarios, type-mapping scenarios, preserved defects, command evidence and review status |
| Context/recovery | Bounded packets, dependency ordering, task ownership/heartbeat/release, interrupted-job recovery, SQLite backups |

The base mapper is lexical: **candidate calls are not resolved semantic calls**.
The optional Roslyn adapter needs the .NET SDK and matching references/defines.
It is a standalone compilation adapter, not an evaluated MSBuild solution.

SQLite snapshots cover schema and data values for configured tables. Other
engines need real export/capture adapters. Snapshot equality alone does not prove
rollback/concurrency correctness: define scenarios that exercise those behaviors.
Browser checks compare selected observations or exact screenshot hashes; they
do not inspect every UI state automatically. Authentication, reset/seed logic,
external integrations and test environments must be configured for your app.

## Commands you will use

```sh
python3 run_modernizer.py --manifest /path/control/migration.json scan
python3 run_modernizer.py --manifest /path/control/migration.json map
python3 run_modernizer.py --manifest /path/control/migration.json list map_nodes
python3 run_modernizer.py --manifest /path/control/migration.json map --format mermaid --output application-map.md
python3 run_modernizer.py --manifest /path/control/migration.json next-action
python3 run_modernizer.py --manifest /path/control/migration.json command build-java
python3 run_modernizer.py --manifest /path/control/migration.json command-status JOB_ID
python3 run_modernizer.py --manifest /path/control/migration.json report
```

`command` starts a background worker; `--wait` is available for CLI scripts.
Jobs execute only configured commands, without a shell. They may write/build/run
code within that configured scope, so review commands before allowing execution.
`run SCENARIO_ID` compares a registered scenario; observation runs can take as
long as their configured capture deadlines. Their records survive interruption.
`report` returns exit 0 even when gaps exist; inspect its contents.

Detailed record shapes, adapter setup and gates are in `docs/v0.2-workflow.md`.
Original feature/question/defect records remain compatible with 0.1. Existing
ledgers are extended with an additive command-job table. Updated verifier code
invalidates prior evidence intentionally; rerun comparisons after upgrading.

## Try the included examples

- `python3 demo.py`: dependency-free synthetic HTTP ledger demo, not a compiled
  C#/Java migration.
- `python3 -m unittest tests.test_workflow -v`: exercises the entire declared
  evidence workflow with real SQLite snapshots, background processes and
  simulated build outputs. The simulated build is explicitly a test fixture.
- `examples/invoice`: real source for a small .NET/Razor application and its
  Java/React reference counterpart. Includes manifest, map and preparation
  script. Follow its README; actual builds need your .NET SDK, JDK, Node and
  frontend/browser dependencies. This reference pair is not auto-generated by
  a migration agent and has not been compiled in this environment.

## Context, state and resilience

The default packet cap is 60,000 serialized JSON bytes, not a token estimate.
Leave room for client instructions, reasoning and output. Packets include source,
contracts, dependencies, type mappings, plans, scenarios and defects. Oversized
packets fail explicitly; split work without dropping requirements.

Keep the manifest and `.migration/ledger.sqlite3` with your control project.
A new coding session reads saved state and resumes eligible work. Use heartbeat
for a long-lived lease; use release with its token when switching clients or
replanning. Release keeps edits. Without the token, wait for expiry and recover.
Background commands continue while their worker lives; a dead worker never
becomes a pass and is marked interrupted after expiry. No requests replay
implicitly. Protect external side effects with isolated fixtures and idempotency.

Use `backup PATH` for a consistent SQLite backup. Also preserve source/target
repositories, manifest, fixture files, build artifacts and relevant dependencies
on independent storage. Local WAL/checkpoints cover process restarts, not lost
machines. This release does not implement active machine failover or unattended
model hosting. Native client sessions provide model execution.

## Validation limits

The Python engine/CLI/MCP and SQLite adapter run here. Native Claude/Copilot
sessions, Roslyn/.NET compilation, Java compilation, React builds and a real
browser capture remain unverified in this environment: the corresponding client,
SDK/compiler/packages/browser binaries are absent. The Playwright launch check
failed on a missing Chromium executable, and did not produce parity evidence.
`VALIDATION.md` records the actual checks. Do not interpret tests of the engine
as proof that a real application's migration is correct.

`ready_for_acceptance` means the configured gates and reviewed file inventory
pass. `complete` remains false: unobserved runtime behavior and final user
acceptance cannot be established by an automated score.

Official integration references: [Claude subagents](https://code.claude.com/docs/en/sub-agents),
[Copilot custom agents](https://code.visualstudio.com/docs/agent-customization/custom-agents),
[Claude MCP](https://code.claude.com/docs/en/mcp),
[VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers).
