# Deployment readiness review

Reviewed 8 October 2026, starting from local commit `d4e9c29`.

**Decision: staging candidate; public production remains gated.** The local checks pass after the fixes below. The current revision needs a successful remote CI run and acceptance on the chosen hosting environment before promotion.

## Findings fixed

| Priority | Finding | Resolution |
| --- | --- | --- |
| High | Invalid startup configuration could include raw input values, including credentials, in the printed validation exception. | Hide input values in settings validation errors. Regression cases cover model-level and field-level failures using synthetic secrets. |
| High | The worker could update its heartbeat and begin processing while its schema was incompatible; API readiness already rejected that schema. | Share the schema check with the API and run it before each worker iteration. Missing, older and newer revisions prevent heartbeat updates and all processing; the worker retries after migrations. Six regression cases cover API rejection and worker recovery. |
| Medium | Render pinned Python 3.12.10, predating current security patches. | Request 3.12.15 in Render and CI. CI uses `actions/setup-python`, whose published Linux catalog includes that patch; the pinned uv download catalog does not yet include it. Local Windows runtime qualification remains 3.12.10. |
| Medium | Container CI tested only the API, and release notes incorrectly said that no remote repository or CI run existed. | Add worker heartbeat and Render schema checks to CI. Correct release evidence to distinguish the successful earlier commit from the current candidate. |

Settings errors remain sensitive objects: code should not serialize their raw `.errors()` input dictionaries to logs. This change protects the normal printed startup exception, not arbitrary serialization of credentials.

## Verified evidence

- Full local backend run: **117 passed, zero skipped**, including **19 PostgreSQL tests**, with **83% coverage**. Includes API/worker subprocess restart and the eight new deployment regression cases. [JUnit report](validation/deployment-backend-tests.xml).
- Ruff lint and formatting pass. Both dependency audits report zero known vulnerabilities: [Python](validation/deployment-python-audit.json), [npm](validation/deployment-npm-audit.json).
- Updated Render Blueprint passes the published schema. [Schema validation](validation/render-blueprint.json).
- Release wheel/source build and isolated installed-wheel smoke pass; artifacts are checked against the current application source. [Manifest](validation/release-manifest.json), [smoke report](validation/release-smoke.json).
- Existing browser baseline: **29 workflows passed**, followed by **8 UI polish checks**. UI assets did not change in this deployment review; those browser checks were not rerun here.
- [GitHub Actions run 37754352899](https://github.com/bitwindamountains/TindaBot/actions/runs/37754352899) passed for remote `main` at `334152c3ef050fc488ddb608150f8bdc27eae965`, including tests, browser checks, audits, wheel smoke and Docker API readiness. That commit predates the journal, delivery recovery, handover and current review changes. [Recorded CI evidence](validation/deployment-remote-ci.json).
- Production credentials and privacy configuration are absent locally. No hosted resources or live provider deliveries were created during this review.

## Required before public production

1. Push the reviewed candidate and pass its full CI, including Python 3.12.15 and the API/worker containers. Docker is unavailable on this local machine.
2. Configure the selected hosting account, TLS PostgreSQL database, independent operator credentials, real Meta/Sheets/SMTP credentials and actual shop/privacy policies. Keep customer traffic disconnected while staging.
3. Apply migration `0003`; deploy matching API and one worker. Verify HTTPS readiness, authenticated health and a complete test checkout through Meta, Sheet projection, seller email and handover with permitted accounts.
4. Verify hosted backup/restore, monitoring notifications, compatible application rollback and the documented supervised seller pilot. Follow the [deployment handoff](DEPLOYMENT.md) and [remaining launch gates](RELEASE_STATUS.md#remaining-launch-gates).

The worker schema check prevents work beginning on an already incompatible schema; it is not a lock against an operator changing the schema during an iteration. Coordinated migrations and compatible API/worker promotion remain required.
