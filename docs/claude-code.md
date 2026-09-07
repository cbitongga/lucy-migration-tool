# Claude Code setup

Version 0.2: use the main `migration-coordinator` agent and the seven native role
definitions now included. README.md and v0.2-workflow.md supersede the historical
alpha-capability descriptions below. CLI command: `claude --agent migration-coordinator`.


This integration targets **Claude Code**, the terminal coding agent. The local
stdio server is not an integration with the ordinary Claude web chat. Both
Copilot and Claude Code use the same tools, application manifest, and ledger.

## Connect from the extracted tool folder

1. Install/authenticate Claude Code through your normal setup. Python 3.11+ is
   needed for this tool. There is no separate model API key required by the
   migration engine; Claude Code's own subscription/authentication still applies.
2. Register your application directories with `init` as described in README.md,
   or retain the exact manifest already used by Copilot. Do not initialize a
   second ledger just to switch clients.
3. From the extracted `migration-workbench` folder, run:

   ```sh
   python3 run_modernizer.py --manifest /absolute/path/migration-control/migration.json claude-config --output .mcp.json
   ```

   Replace the example manifest path with yours. This writes Claude's
   `mcpServers` format, using absolute interpreter/script/manifest paths. Existing
   unrelated servers/settings are preserved, and a backup is made before a
   changed existing file is replaced. Repeating identical setup is a no-op.
   A conflicting migration-workbench entry is rejected for explicit review.
   Omit `--output` to inspect the JSON without writing any configuration.
4. Start Claude Code from that same tool folder and grant the application and
   control folders as additional working directories:

   ```sh
   claude --add-dir /absolute/path/legacy-app --add-dir /absolute/path/modern-app --add-dir /absolute/path/migration-control
   ```

   Add each backend/UI/shared-library root if there are more than two. These
   editor-access directories are distinct from the engine's manifest roots;
   configure both intentionally. Existing organization policies still apply.
5. In Claude Code, use `/mcp` to inspect the migration-workbench connection and
   complete any client server-trust prompt. The root `CLAUDE.md` imports the
   shared workflow from `.github/copilot-instructions.md`.
6. Ask Claude to read the migration report, inspect discovered candidates and
   unresolved questions, and resume the next eligible feature using its packet.

Configuration is local to the extracted tool project. If launching from another
project, generate its `.mcp.json` there and merge the shared workflow into its
existing `CLAUDE.md`; do not overwrite its rules. Do not rely on the instructions
from an additional directory being loaded automatically. The generated absolute
paths are machine-specific; regenerate after moving the tool.

## Switch between Copilot and Claude Code

Use the same absolute manifest path in both generated configurations. Stop
mutating work in the first session before starting in the second. A new session
can read all recorded features, questions, preserved bugs, and reports. To resume
an active lease, retain its token; without it, wait for expiry and call recover.
Do not erase state, invent a new feature ID, or rewrite a lease to bypass it.

The shared engine enforces source/target evidence freshness and packet limits,
regardless of which agent invokes it. Run evidence invalidates after changes to
the fingerprinted engine files in this update, so reverify prior comparisons.

## Verification and limitations

The generated Claude configuration is tested by actually launching its command
in a different working directory, performing the MCP handshake, and querying
the ledger. Tests also exercise CLI-to-MCP session handoff and configuration
preservation/conflict handling. Claude Code itself is not installed in the
development environment; its live connection and UI have not been tested.

The server negotiates MCP 2025-11-25 or 2025-06-18. If your client cannot use these
versions, use the CLI while the protocol adapter is upgraded. Claude Code does
not change the alpha limitations: discovery is heuristic; HTTP scenarios are
bounded; UI/database parity and automatic translation remain unimplemented.

Official references: [Claude Code MCP setup and project configuration](https://code.claude.com/docs/en/mcp),
[CLAUDE.md imports](https://code.claude.com/docs/en/memory).
