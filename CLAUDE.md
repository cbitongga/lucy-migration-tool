# Migration Workbench for Claude Code

@.github/copilot-instructions.md

Run the main session with --agent migration-coordinator to delegate to the
provided discovery, planning, backend, UI, verification and review subagents.
Use the same migration.json path as Copilot. Start with migration_next_action.
Read README.md and docs/v0.2-workflow.md for setup and current limitations.
Do not create a second ledger when switching clients. Preserve existing leases
and use one mutating agent session per workspace at a time.
