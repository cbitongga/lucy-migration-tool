# Validation of 0.2.0

Environment: Linux, Python 3.12.13. Command:
`python3 -m unittest discover -s tests -v`

**48 tests passed in 12.251s**, no skips or failures. Twelve new workflow tests
extend the prior 36 tests. They exercise real SQLite snapshots and temporary
files, foreground/background subprocesses and the saved pipeline gates.

Verified additions:

- Source graph locates route/type/exception evidence and ignores a route in a
  C# comment; graph nodes/edges are still labeled as lexical candidates.
- File disposition becomes stale when its source changes.
- A declared feature progresses through plan/stages/build/capture/review gates.
- Simulated build execution creates and fingerprints a fixture artifact;
  corrupting that artifact invalidates the build gate.
- A detached command completes after the caller closes and reopens the engine.
- Command failures, timeouts and output overflow never produce passes.
- Releasing a lease preserves target edits and allows a new claim.
- SQLite captures detect changed decimal text and null-to-empty differences.
- A changed characterized legacy baseline blocks even when both systems match.
- Tracked database changes stale prior evidence.
- Typed JSON comparison distinguishes integer, decimal, boolean, string and null;
  duplicate object keys are rejected.

Additional checks:

- Browser adapter JavaScript passed `node --check`.
- An actual Playwright launch attempt failed because Chromium binaries are
  absent; no browser parity pass was recorded.
- The reference sample's doctor check reported missing dotnet and javac.
- Sample preparation registered the graph/feature/type mapping/plan/defect and
  correctly left RuntimeBaseline as an unanswered blocking question.
- A sample application map was generated in JSON and Mermaid Markdown.

Not verified: live Claude/Copilot subagent execution, Roslyn adapter compilation,
.NET/Java compilation, React build, actual browser capture, production database
engines, arbitrary legacy application migration, or whole-program equivalence.
The SQLite/build fixtures validate engine mechanics, not a real .NET-to-Java
migration. No native application has been declared fully migrated.

The final CLI output-file behavior prints a compact saved-path receipt; map/report
content is written to the requested artifact instead of flooding chat output.

---

The following sections retain historical validation evidence for 0.1.1/0.1.0.

# Validation of 0.1.1

The updated suite passed **36 tests in 10.140s**, with no skipped tests or
failures, on Python 3.12.13/Linux. Six client checks were added to the 30 engine
and protocol tests described below. They cover generated Claude configuration
launching a real MCP subprocess from a different working directory (including a
path with spaces), reading an existing feature lease, preserving unrelated
configuration and its backup, idempotent setup, conflict rejection, malformed
configuration preservation, CLI config output, and shared instruction wiring.

Claude Code is not installed in this environment. The generated configuration
and MCP handoff are verified; live Claude Code and Copilot UI connections are
not. No model/API calls were made. This update preserves the alpha's migration
limitations. The prior demo results below are historical 0.1.0 evidence.

## Prior 0.1.0 baseline

Validated in this workspace using Python 3.12.13 on Linux.

## Automated checks

Command: `python3 -m unittest discover -s tests -v`

Result: **30 tests passed**, no skipped tests or failures. Final test run:
`Ran 30 tests in 9.405s — OK`.

The suite exercises real temporary directories and SQLite databases, paired
local HTTP servers, and a real stdio MCP subprocess. Specific cases include:

- A newly opened engine resumes and completes an existing task lease.
- A second process cannot claim an unexpired owned task.
- Expired tasks return to ready; interrupted comparisons never count as passes.
- Oversized packets/responses fail explicitly without silent truncation.
- Missing source ranges, traversal, symlink references, and missing target files
  are rejected.
- Source changes invalidate a claim; target changes invalidate implementation.
- Target build outputs do not incorrectly invalidate a source-only work claim.
- Blocking unanswered questions and unimplemented dependencies stop execution.
- Dependency cycles are rejected and missing dependencies remain visible.
- A consistent SQLite backup passes integrity_check and retains task state.
- Exact matching responses pass; numeric precision loss, status differences,
  and selected-header differences fail.
- Two matching outages fail to satisfy a characterized healthy legacy fixture.
- A newer failed run overrides an older passing run.
- Changes during comparison make evidence stale.
- HTTP passes cannot establish declared UI or database verification.
- MCP initialization, tool listing/calls, notifications, invalid argument types,
  and supported-version negotiation work over newline-delimited JSON-RPC.

## Demonstration

Command: `python3 demo.py --output <fresh-temporary-directory>`

Result: process exit 0. Matching response passed; simulated precision regression
failed; restored legacy-compatible response passed; reopening the ledger resumed
the task. The final report retained `complete: false` and unsupported database/UI
dimensions. JSON report/evidence and a consistent backup were produced.

The demonstration uses synthetic Python HTTP services and inert C#/Java source
fixtures. It is not evidence of a compiled or migrated .NET application.

## Integration check and limits

`vscode-config` emitted a valid stdio server configuration with absolute local
Python, entry-point, and manifest paths. These paths are generated on the user's
machine during setup and are not portable hardcoded settings.

Not tested: a live VS Code/Copilot session, Windows/macOS execution, actual
C#/.NET compilation, Java/React generation, browser behavior, database writes,
production integrations, very large repository performance, hostile/local
multi-user access, or the newest stateless MCP protocol. No end-to-end
application migration has been performed. The README records the alpha's scope
and next milestones.
