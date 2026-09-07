# Application modernization: requirements, proposed design, and open questions

Status: design proposal, not an implemented tool. User requirements below are confirmed; architecture choices are recommendations pending validation against the actual repositories and environment.

## Confirmed requirements

- First migration: legacy C#/.NET backend and frontend to Java backend and React frontend.
- Long-term goal: support additional source and target languages through adapters.
- Repositories are added as folders in a VS Code workspace; the user works through GitHub Copilot.
- Both old and new systems can run in test environments. Environment details and other evidence are not yet available.
- Preserve existing features and observable behavior, including bugs and issues. Document defects; offer optional fixes at the end. Never silently fix legacy behavior during migration.
- Scope: backend application code, UI, and application database interactions. Production cutover, infrastructure migration, and database redesign are not currently included.
- The user can provide the database schema later and expects schema information in source models. Treat that as a discovery lead, not a verified complete schema.
- Include explicit treatment of data types, folder structure, data processing, exceptions, and engineering practices.
- Measure migration coverage and correctness against the legacy application.
- Work must continue across context resets without depending on a model's maximum 1M-token context.
- Record missing information and ask for clarification; do not invent behavior, requirements, or environment details.

## Recommended product form

[Likely] Use a standalone migration engine with a command-line interface, expose its operations to Copilot through MCP, and provide Copilot skills/instructions for the workflow. Add a thin VS Code extension when a dedicated explorer, diff navigation, and progress UI are useful.

| Option | Strength | Limitation | Recommendation |
| --- | --- | --- | --- |
| Copilot skills and scripts | Fits the user's existing workflow; teaches repeatable procedures | Instructions alone cannot enforce durable state, evidence freshness, or completion gates; scripts need an execution core | Use as the workflow layer |
| VS Code extension containing all logic | Strong editor interaction and workspace integration | Couples core migration operations to the editor lifecycle and complicates reuse outside it | Keep the extension thin |
| Standalone engine, MCP integration, and Copilot skills | Centralizes state and verification; supports restart, CLI use, and later CI integration | Requires an execution core, persistence, and an explicit AI execution model | Recommended foundation |

VS Code supports MCP tools and extension-contributed language model tools. Agent Skills can package instructions, scripts, and resources. These are integration capabilities, not migration correctness guarantees. Sources: [MCP integration](https://code.visualstudio.com/docs/agent-customization/mcp-servers), [extension tools](https://code.visualstudio.com/api/extension-guides/ai/tools), and [Agent Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills).

The engine owns inventories, jobs, dependencies, evidence, and gates. Copilot proposes changes and invokes tools; the engine checks preconditions and verifies outcomes. Build, scan, and comparison jobs can run separately from chat and return durable job IDs. An MCP server does not by itself supply an unattended Copilot reasoning loop. Initially, AI work resumes through an active Copilot session; fully unattended generation requires a separately selected, authorized model runner and its authentication, policy, and cost constraints.

## Proposed components

1. Workspace manifest: explicitly identifies each source and target root, repository revision, application relationship, build variant, and permitted output location. Do not infer root roles from folder order.
2. Discovery adapters: use language-aware parsing and build metadata alongside runtime evidence. Record endpoints, UI pages, events, jobs, configuration, dependencies, models, SQL, mappings, and exception paths.
3. Behavior catalog: assigns stable IDs to discovered features and contracts; links each claim to exact source revision and location or a reproducible runtime observation. Records facts, hypotheses, conflicts, and unknowns separately.
4. Migration planner: creates dependency-aware tasks and a proposed Java/React architecture. Backend framework, Java version, React tooling, and JavaScript versus TypeScript remain open decisions.
5. Execution coordinator: issues bounded work packets, stages target edits, detects conflicts, records attempts, and resumes interrupted work. Specific engine implementation language remains undecided.
6. Verification harness: executes the same scenarios against isolated legacy and target environments and compares observable outcomes.
7. Evidence and reporting store: persists task state and structured results transactionally; exports readable reports and traceability records. SQLite is a candidate for a local single-user implementation, not a confirmed requirement.

## Workflow and decision gates

1. Register the workspace and pin source revisions. Record uncommitted input changes if they are included in the baseline.
2. Discover features and dependencies. Reconcile every relevant source area with a feature, support function, generated artifact, or an explicitly reviewed disposition. Reflection, dynamic loading, unavailable packages, conditional builds, and external behavior remain visible gaps.
3. Establish the executable legacy baseline. Build characterization tests around observed behavior, including known defects; do not create expected outputs solely from the new implementation.
4. Review the inventory, unresolved questions, proposed target architecture, and observable equivalence boundaries. Block only affected work when missing information does not affect other tasks.
5. Migrate one vertical slice through UI, backend, and persistence. Verify the complete slice before expanding the migration.
6. Migrate remaining dependency groups with local checks and recurring integration comparisons. Avoid translating one file at a time without its behavior and dependencies.
7. Reconcile the whole inventory, run full-system comparisons, and report remaining mismatches, blocked cases, and evidence limitations.
8. Present the preserved-defect register. Optional fixes are separate changes with separate tests and an explicit approved departure from the compatibility baseline.

These gates are proposed product behavior, not additional permission requests for this design document.

## Exact-equivalence policy

[Certain] Preserving every possible behavior cannot be demonstrated from repository analysis or finite testing alone. The deliverable should report verified parity against a versioned inventory and scenario set, plus remaining uncertainty. Never label an AI confidence estimate as proof of completeness.

Observable contracts include inputs, outputs, validation order, errors, UI interactions, navigation, authentication, authorization, database changes, transaction outcomes, retries, external calls, and other side effects. Internal organization may change where it does not alter those contracts.

Exact compatibility and engineering improvements can conflict. Preserve the legacy behavior in clearly documented compatibility code when necessary; retain clean structure around it. Do not use a best-practice rule as permission to change externally visible behavior.

For each discovered defect, record an ID, legacy evidence, reproduction scenario, impact, migrated location, parity test, and proposed optional fix. Classify unconfirmed suspected defects separately. Default disposition is preserve. Security-sensitive findings are documented and included in the final decision record; they are not silently repaired or omitted.

Cross-language implementation details such as native stack traces, process timing, and internal exception classes cannot automatically be identical. Discover which details are externally exposed and clarify how they must be reproduced. Do not silently normalize their differences.

## Data and language semantics

[Certain] Source models are not guaranteed to be the full live database contract. Inspect ORM configuration, migrations, embedded SQL, and database projects as well. Microsoft documents distinct approaches where a model or a database is the source of truth: [Managing database schemas](https://learn.microsoft.com/en-us/ef/core/managing-schemas/).

Before claiming database parity, reconcile source evidence with the supplied schema and relevant runtime behavior. Request constraints, defaults, identities/sequences, indexes, triggers, views, stored procedures, permissions, collation, and transaction behavior where used. Unknown objects or schema drift block the affected parity claims. No production schema writes are required for discovery.

Create a reviewed mapping for each used type and operation, including:

- Integer ranges, unsigned values, overflow behavior, decimal precision/scale, floating point, and rounding.
- Null versus missing versus empty; default values; enum values and unknown values.
- Date/time interpretation, time zones, locale, culture-dependent parsing, and formatting.
- String comparison, casing, encoding, collation, identifiers, GUIDs, and binary data.
- JSON field names and omission rules, numeric representation, pagination, collection ordering, and timestamps.
- ORM tracking, lazy loading, query semantics, transactions, isolation, rollback, concurrency, retries, and duplicate handling.
- Exception handling and mapping to status codes, response bodies, UI messages, logs, and partial side effects.
- Numeric values crossing the Java-to-React boundary, with explicit tests for precision loss in the browser.

Do not apply blanket substitutions such as every numeric type becoming a floating-point number. A mapping is complete only when its operations and serialization behavior are tested, not just its declarations.

## Context-independent execution

The database and evidence files are authoritative. Chat history and generated summaries are disposable navigation aids.

Each work packet contains a stable task ID, source hashes, a bounded set of relevant symbols and callers/callees, approved contracts, type mappings, preserved defects, dependency interfaces, expected outputs, test IDs, and unresolved questions. Full source evidence remains retrievable by reference; summaries do not replace it.

- Budget packets below the actual model limit, reserving room for tool results and reasoning/output. Choose the working budget empirically; never require 1M tokens.
- Retrieve by symbol, dependency, and feature links plus textual search. Semantic retrieval can assist discovery but cannot serve as the completeness ledger.
- Split large tasks by cohesive behavior. When dependencies form a cycle, plan and validate the group together, with bounded subtasks sharing a versioned contract.
- Reject or flag work that exceeds its packet, discovers unresolved contract changes, or relies on unavailable evidence. Expand discovery or split work instead of silently truncating inputs.
- Persist a state machine: discovered, blocked, ready, in progress, implemented, verified, and accepted. Implemented does not mean verified; acceptance needs explicit review.
- Record source/target hashes, fixtures, configuration, test-tool versions, and result artifacts for each verification. Changes invalidate affected evidence through the dependency graph.
- Use transactional checkpoints, job leases, and staging so a crash does not mark partially written work complete. Resume reconciles actual files and job state before continuing.
- Make retryable operations idempotent; do not blindly repeat external side effects. Use isolated fixtures and test endpoints.
- Test recovery with a new chat and an interrupted worker. Machine-loss recovery requires backups of repositories, state, and evidence on independent storage; local checkpoints alone are insufficient.

## Measuring migration quality

Do not collapse status into an unqualified single score. Always show numerator, denominator, baseline version, blocked cases, and stale evidence.

| Measure | Definition / evidence |
| --- | --- |
| Source disposition coverage | Relevant discovered source units assigned a reviewed disposition / all relevant discovered units; this is accounting, not proof that all runtime features were found |
| Feature implementation coverage | In-scope baseline features with mapped target implementations / all in-scope baseline features |
| Feature verification coverage | Baseline features whose required current scenarios all pass / all in-scope baseline features |
| Behavioral parity | Passing differential scenarios / all required scenarios; report failed, blocked, skipped, and unrun separately |
| Data parity | Verified assertions about stored values, constraints, reads, transactions, and side effects / all required data assertions |
| UI parity | Verified interaction, navigation, content, error, role, and agreed visual scenarios / all required UI scenarios |
| Preserved-defect coverage | Confirmed legacy defects with passing compatibility tests / all confirmed in-scope defects |
| Evidence freshness | Verification records matching current source, target, configuration, and fixtures / required verification records |
| Operational comparison | Observed latency, throughput, resource use, and failure/recovery behavior against the baseline; acceptance criteria still need clarification |

Feature denominators are versioned. Newly discovered features enter the ledger and may lower coverage; do not hide them or remove difficult cases to improve a score. Show approved exclusions explicitly. Code coverage is supplementary evidence, not feature completeness.

Proposed completion criteria: all in-scope inventory entries accounted for, all required parity scenarios passing with current evidence, no unresolved required-contract questions, no unapproved behavioral differences, and explicit user acceptance. Approval of a deviation changes the contract and must be disclosed; it does not count as exact original parity.

Differential runs start from equivalent isolated database snapshots and the same input fixtures. Compare responses, data mutations, external requests, emitted events, and error outcomes. Exercise failures, boundaries, roles, multi-step workflows, and relevant concurrency scenarios. Capture nondeterminism such as clocks and generated IDs; any comparator normalization must be explicit and approved so it cannot hide defects. Visual tolerances and performance tolerances remain unresolved.

## Open questions register

All questions below are unanswered unless marked as already confirmed above. Discover answers from repositories where possible, attach evidence, and ask the user about remaining gaps. The user does not need to answer this register now.

| ID | Question | Needed before |
| --- | --- | --- |
| Q01 | Which .NET versions and frontend technologies are present: MVC/Razor, Web Forms, Blazor, desktop UI, or another technology? | Selecting discovery and UI migration adapters |
| Q02 | Which workspace roots are legacy backend, legacy UI, shared libraries, and target repositories? How many applications and which revisions/build variants are in scope? | Baseline inventory |
| Q03 | What are the build/start commands, OS requirements, package feeds, licenses, and configuration dependencies? | Executable baseline |
| Q04 | Which Java version and backend framework are required? Are there organization-approved project templates, build tools, and dependency policies? | Target scaffold |
| Q05 | Does React use TypeScript or JavaScript? What routing, rendering, component library, browser support, and repository conventions are required? | Target UI scaffold |
| Q06 | Must the UI preserve appearance and layout exactly, including responsive states, keyboard interaction, downloads/printing, and accessibility behavior? | UI acceptance contract |
| Q07 | What unit, integration, end-to-end, manual test, specification, and production-incident evidence exists? Who reviews the feature inventory? | Verification plan |
| Q08 | How can both applications be started, reset, authenticated to, and exercised in test environments? | Differential execution |
| Q09 | What sanitized datasets and boundary cases are available, and can isolated copies be created for each system? | Data verification |
| Q10 | Which database engine/version is used, and when can the complete schema, database objects, and representative configuration be supplied? | Database parity claims |
| Q11 | Is the model code-first, database-first, manually mapped, or mixed? Are migrations and SQL/database projects checked in? | Schema reconciliation |
| Q12 | Which external services, identity providers, shared sessions, queues, files, scheduled jobs, and reports participate? Are test endpoints or faithful fixtures available? | Integration contracts |
| Q13 | What roles, permissions, tenants, feature flags, locales, and deployment configurations must be covered? | Coverage baseline |
| Q14 | Which known bugs and issues must be seeded into the preserved-defect register? Are error payloads, headers, and stack traces externally consumed? | Compatibility tests |
| Q15 | What precision, rounding, time-zone, ordering, timeout, transaction, and concurrency behaviors are contractual? Which can be demonstrated from the old system? | Semantic mapping |
| Q16 | How should nondeterministic values and timing be compared? What visual and performance tolerances, if any, are acceptable under exact-equivalence requirements? | Comparator approval |
| Q17 | Which VS Code/Copilot versions and organization policies apply? Are MCP servers, custom skills, local executables, and extensions permitted? | Integration implementation |
| Q18 | Must AI generation use only an active Copilot session, or is a separately authenticated unattended runner allowed? What execution and cost limits apply? | Automation model |
| Q19 | Where may target files be edited, which review checkpoints are desired, and may the tool create branches or commits? | Automated edits |
| Q20 | Where should migration state and evidence persist, how long should they be retained, and is recovery on another machine required? | Recovery implementation |
| Q21 | Which concrete engineering standards, static analysis gates, dependency rules, and folder conventions apply? How should conflicts with preserved behavior be reviewed? | Target standards |
| Q22 | Who accepts the final parity evidence and decides whether optional defect fixes proceed? | Acceptance and optional remediation |

## First implementation milestone

Build discovery, persistent traceability, and a differential test harness around one representative UI-to-database flow before building broad translation automation. That milestone should demonstrate a preserved legacy defect, a tested type boundary, an error/rollback path, and successful resumption from a fresh context. Unsupported constructs must be reported as gaps. This validates the evidence process before scaling to the entire application.
