# Reference invoice migration

This is a small .NET 8/Razor source application and a Java/React reference
counterpart. It demonstrates a decimal larger than JavaScript's safe integer
range and a deliberately preserved error-message typo. It has no database;
SQLite data-parity execution is exercised separately by tests.test_workflow.

The reference target was authored with this package. It is not an output of
an unattended migration-agent run, and the native application pair has not been
compiled or browser-tested in this environment. Prerequisites are missing here.

## Prepare

From the tool root, run:

```sh
python3 examples/invoice/prepare.py
python3 run_modernizer.py --manifest examples/invoice/control/migration.json doctor
```

prepare.py refuses to overwrite an existing feature ledger. It registers one
feature, its type mapping, preserved defect, plan and scenarios. RuntimeBaseline
remains an unanswered blocking question: the expected sample outputs are declared
fixture expectations and must be confirmed against the running legacy app.

The map JSON/Markdown included in control is a captured reference illustration.
Regenerate it after preparation to match your paths, decisions and current files.

## Install prerequisites and build locally

Use an installed .NET 8 SDK, JDK 17+, a supported Node runtime, and npm. For the
frontend run npm install in target/frontend, review the resolved dependencies,
and retain the resulting package-lock.json; subsequent installs should use npm ci.
This sample uses React 19.2 and Vite 7 ranges to resolve compatible patches on
first install. No lockfile could be generated/verified here. These are sample
choices, not mandated frameworks for your applications.

Install Playwright into the tool's Node module resolution path and install its
Chromium browser through your normal approved dependency setup. The adapter
only uses installed packages/binaries; it never downloads them itself.

Run the manifest's build-csharp, build-java and build-react commands with command
NAME --wait. They require expected compiled artifacts. Do not substitute echo
commands or fabricate successful results if a compiler/dependency is unavailable.

## Run the systems

In separate terminals:

- legacy: dotnet run (serves http://127.0.0.1:5100)
- target/backend: java -cp build InvoiceServer (API on http://127.0.0.1:8100)
- target/frontend: npm run preview (UI on http://127.0.0.1:4173)

Verify the expected API and browser fixtures against the actual legacy service,
update the manifest's build IDs, and answer RuntimeBaseline with the observations
and provenance. Attach the manifest to Copilot or Claude's migration coordinator.
It will inspect the supplied reference code, record backend/UI stages, run the
required builds and HTTP/browser checks, and request review.

The three API fixtures cover invoice 42, missing ID and unknown ID. The browser
fixture covers the empty-input error. Other methods, duplicate query parameters,
loading races, every browser, every navigation state and exact layout are outside
these fixtures; do not claim universal parity from this example.

Official context: React 19.2 is documented at
https://react.dev/blog/2025/10/01/react-19-2 and Vite setup at
https://vite.dev/guide/. Choose your organization's supported versions for real
migrations rather than treating this lab as a platform standard.
