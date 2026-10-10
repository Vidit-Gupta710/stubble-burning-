# AGENTS.md

Rules for any AI coding agent working in this repo. Read fully before writing code. Re-read the "Golden rules" at the start of every phase.

## Project

**Stubble Burning Early Warning** (hackathon, Air track). The system pulls NASA FIRMS fire hotspots, Open-Meteo wind and boundary-layer forecasts, and OpenAQ station data for Punjab, Haryana and Delhi-NCR. It computes a smoke exposure score per grid cell, district and sensitive site (schools, hospitals), then a Strands agent sends tiered, local-language alerts. A map dashboard shows officials the fire clusters and the predicted smoke path.

Hackathon rule: must use AWS open source tools and/or AWS services. We use both.

## Stack (do not swap without asking)

- **Language/tooling:** Python 3.12, Pydantic, numpy, pytest, ruff. Frontend: React + Vite + Tailwind + MapLibre.
- **AWS open source:** Strands Agents SDK, AWS CDK (Python), Powertools for AWS Lambda.
- **AWS services:** Lambda, API Gateway, EventBridge Scheduler, S3, DynamoDB, Bedrock, SNS, Cognito, Amazon Location Service. Athena optional.
- **Never use:** Amazon Pinpoint (being retired). No SMS in the demo (India sender registration needed); use email, Telegram, Twilio WhatsApp sandbox.
- Pin all dependency versions. Model id and region come from environment variables.

## Golden rules (in priority order)

1. **Phase gate.** Work on exactly one phase at a time, in order. Do not start phase N+1 until phase N's "Done when" check passes with evidence. No jumping ahead, no "while I'm here" extras.
2. **Verify everything.** After every code change, run it and check it. Never write "should work". Show the command output.
3. **Minimal code.** Write the least code that meets the requirement. After it works, look for ways to shrink it (rules below), then re-verify.
4. **Never guess external facts.** Check official docs for API parameters, endpoints, variable names and limits before coding a client. If you cannot verify, say so and make it configurable.
5. **Safety and ethics are not optional.** Section "Safety" below overrides convenience.

## Phases

| # | Phase | Done when |
|---|-------|-----------|
| 1 | Scaffold repo + CDK app (empty stacks: data, ingest, agent, API). Makefile: `test`, `deploy`, `replay` | `cdk synth` runs; `pytest` runs one sample test |
| 2 | `clients/firms.py`: FIRMS area CSV client, typed model, cache raw to S3 or `/data` | One past day fetched; hotspot count printed; file saved |
| 3 | `clients/weather.py`: Open-Meteo hourly wind speed, direction, boundary layer height on a coarse grid + interpolation | Interpolated value matches a direct query within tolerance |
| 4 | `clients/aqi.py`: OpenAQ v3 stations, PM2.5 series, handles missing data | One week of station data saved |
| 5 | Geo utils: district tagging, haversine, bearing, 0.1 degree grid, cropland filter hook | Unit tests on known coordinates pass |
| 6 | `core/exposure.py`: vectorised numpy exposure model, config-driven constants and tiers | Upwind fire scores high; downwind near zero; calm wind and low mixing height raise score; 2000 fires x 3000 cells under 3 s |
| 7 | `scripts/backtest.py`: past-season exposure vs later PM2.5 at lags 0 to 48 h; chart; threshold suggestions | Chart + summary saved; thresholds written to config |
| 8 | DynamoDB tables in CDK + repositories; load sites from OSM Overpass + 10 seeded demo sites | Seed command fills tables; counts printed |
| 9 | Lambdas (Powertools): ingest, exposure; EventBridge every 3 h; REPLAY flag | Manual invoke in replay mode writes exposure rows |
| 10 | Strands agent + tools (`get_hotspots`, `get_exposure`, `get_sensitive_sites`, `check_recent_alerts`, `compose_alert`, `send_alert`); dedupe; template fallback if Bedrock fails | Replay run produces alerts for seeded sites; trace logged |
| 11 | Notifier: SNS email, Telegram bot, optional WhatsApp sandbox, dry-run flag, per-user daily cap | Real Telegram message received; dry-run only logs |
| 12 | API Gateway + Lambda read endpoints (`/hotspots`, `/exposure`, `/sites`, `/alerts`, `/backtest`), Cognito for official routes | curl smoke script passes on deployed stack |
| 13 | Frontend: map, clusters, exposure layer, drift arrows, site markers by tier, alert log, backtest chart, replay speed, school console | Full demo flow works in browser on replay data |
| 14 | Impact counters: people covered, sites alerted, acknowledgements, average lead time | Counters match seeded scenario |
| 15 | `scripts/demo.py`, end-to-end test, README (deploy, replay, demo) | One command reproduces demo state; README deploys from scratch |

Stretch items (label OCR, farmer advisory, ML model) only after phase 15 and only if asked.

### Phase gate protocol

1. **Start:** state the phase number and a plan of at most 5 bullets.
2. **Build:** implement only what the phase needs.
3. **Verify:** run the verification checklist below.
4. **Minimise:** run the minimise pass below, then re-run verification.
5. **Report:** post the status block (format below) with real command output.
6. **Stop and wait** for the user's go-ahead. Proceed automatically only if the user has explicitly said to continue through phases, and still only after the gate passes.

If a phase fails its check, fix it inside the same phase. Never move on with a known failure or a skipped check. If blocked, say what is blocked and why.

## Verification checklist (after every code change, not only at phase end)

- Run the code you wrote. For logic, write or update unit tests first or alongside.
- `pytest -q` passes. Do not delete, skip or weaken a test to make it pass; fix the cause.
- `ruff check .` and `ruff format --check .` are clean.
- Infra touched: `cdk synth` succeeds. Check IAM stays least-privilege.
- Frontend touched: `npm run build` and lint succeed.
- Lambdas: invoke locally in REPLAY mode before deploying.
- Read your own diff: remove debug prints, unused imports, commented-out code, leftover TODOs.
- Compare behaviour to the phase's "Done when" line, item by item.

## Minimal code rules

- Before writing, search the repo and the standard library for something that already does the job. Reuse it.
- Prefer numpy vectorisation, comprehensions and stdlib over hand-written loops and helpers.
- No speculative features, config options, abstractions or base classes. One use means no wrapper.
- No duplicate logic. Extract only when the same code appears 3 or more times.
- Keep functions short (about 40 lines max) and files focused.
- Delete dead code, unused parameters and unused dependencies as you go.
- Use Pydantic models for data shapes instead of hand-written validation.
- Short does not mean clever: no code golf, no one-liners that need a comment to decode. Clear names, brief comments only for "why".
- **Minimise pass (end of each phase):** re-read the new code and cut anything that can go without changing behaviour. Re-run the full verification checklist after any cut.

## Architecture rules

- **Pure core:** `core/` (exposure, tiers, dedupe, matching) has no AWS imports and is fully unit tested.
- **Thin handlers:** Lambda handlers parse input, call core or clients, return output. Logic lives elsewhere.
- **Config over code:** exposure constants (sigma, a, b), horizons and tier thresholds live in one config file. The LLM never decides thresholds.
- **Agent boundaries:** tools are small, typed functions. The agent chooses audience and writes messages. It cannot change tiers or bypass dedupe and caps. If Bedrock fails, fall back to templates.
- **REPLAY mode:** every pipeline stage can read saved snapshots (S3 or `/data`) instead of live APIs. Demo must be reproducible.
- **Infra only through CDK.** No manual console resources, except enabling Bedrock model access.
- **Logging:** Powertools structured logs and tracing in every Lambda. Log every agent tool call.
- **Dependencies:** use the AWS SDK for pandas managed Lambda layer for numpy and pandas. Add a new dependency only if the stdlib or existing libraries cannot do the job.

## Safety, privacy, ethics

- Never expose farm-level or farmer-level data. Public views show grid clusters only.
- Opt-in only for alerts, coarse location (pincode or neighbourhood), one-tap unsubscribe, per-user daily cap.
- No real phone numbers or personal data in code, tests, fixtures, logs or the repo. Use fake test data.
- Messages state the reason and the action. They call the output an early-warning index, never an exact forecast.

## Security and cost

- No secrets in code or git. Use environment variables or Secrets Manager. Add `.env` to `.gitignore`.
- Least-privilege IAM per Lambda. No wildcard resources unless unavoidable, and then comment why.
- Stay on the free tier: on-demand DynamoDB, 3-hour schedule, one small Bedrock model. Do not add always-on resources.
- Provide a teardown command or README section.

## Status block (post after every phase)

```
Phase: <n> - <name>
Status: PASSED | FAILED | BLOCKED
Done-when check: <how it was met, with command output>
Verification: pytest <result>, ruff <result>, cdk synth/npm build <result if relevant>
Minimise pass: <what was removed or simplified, lines before/after if useful>
Assumptions: <list>
Open issues: <list or none>
Next phase: <n+1> (waiting for go-ahead)
```

## When unsure

Ask one clear question, or state your assumption and continue only if it is low-risk and reversible. Never invent API parameters, library behaviour or results.
