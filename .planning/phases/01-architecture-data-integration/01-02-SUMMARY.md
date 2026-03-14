---
phase: 01-architecture-data-integration
plan: 02
subsystem: api
tags: [actor-entrypoint, input-validation, free-tier, apify-marketplace, input-schema]

requires:
  - phase: 01-01
    provides: ScraperInput model, FREE_TIER_LIMIT constant
provides:
  - Actor async entry point (main) with input validation and free tier enforcement
  - Aggregator stub for Plan 05 wiring
  - Apify marketplace input schema and actor metadata
affects: [01-05]

tech-stack:
  added: []
  patterns: [actor-context-manager, free-tier-env-detection, global-timeout-asyncio-wait-for]

key-files:
  created:
    - src/main.py
    - src/aggregator.py
    - .actor/input_schema.json
    - .actor/actor.json
  modified: []

key-decisions:
  - "GLOBAL_TIMEOUT_SECONDS=600 (10 min) — aggressive but forces users to scope queries"
  - "Aggregator imported inside try block to keep main.py testable before Plan 05"

patterns-established:
  - "Actor.fail() for validation errors — immediate abort with user-facing message"
  - "Free tier detection: APIFY_IS_AT_HOME=1 AND APIFY_USER_IS_PAYING!=1"
  - "Per-source state tracking via Actor.use_state() with explicit zero counters"

requirements-completed: [INP-01, INP-05, EXE-01, EXE-03]

duration: 1min
completed: 2026-03-14
---

# Phase 1 Plan 02: Actor Entry Point Summary

**Async Actor entry point with ScraperInput validation, free tier cap at 25 results via env detection, 10-minute global timeout, and Apify marketplace input_schema.json with all five parameters**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-14T19:03:43Z
- **Completed:** 2026-03-14T19:04:49Z
- **Tasks:** 2
- **Files created:** 4

## Accomplishments
- Actor entry point (src/main.py) with async main() under Actor context manager
- Input validation via ScraperInput.from_actor_input() and validate_for_mode(), failing fast with Actor.fail()
- Free tier enforcement: when APIFY_IS_AT_HOME=1 and APIFY_USER_IS_PAYING!=1, maxResults silently capped at 25 with info log
- Per-source state initialized via Actor.use_state() with counters for scraped/failed per source
- Startup status message via Actor.set_status_message() for immediate user feedback
- 10-minute global timeout via asyncio.wait_for on aggregator call
- Stub aggregator.py so main.py is runnable before Plan 05 implementation
- .actor/input_schema.json with all five parameters (drugName required, dateFrom/dateTo/severityThreshold/maxResults optional with defaults)
- .actor/actor.json with actor metadata for Apify marketplace

## Task Commits

Each task was committed atomically:

1. **Task 1: Actor entry point with input validation and free tier enforcement** - `209d082` (feat)
2. **Task 2: Apify input schema JSON for marketplace** - `8460e87` (feat)

## Files Created/Modified
- `src/main.py` - Actor async entry point with validation, free tier, timeout
- `src/aggregator.py` - Stub for Plan 05 aggregation pipeline
- `.actor/input_schema.json` - Apify marketplace input form definition (5 parameters)
- `.actor/actor.json` - Actor metadata (name, version, description)

## Decisions Made
- GLOBAL_TIMEOUT_SECONDS set to 600 (10 min) as aggressive default forcing users to scope queries
- Aggregator import placed inside try block to keep main.py independently testable

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- src/main.py ready for Plan 05 to replace aggregator stub
- .actor/ directory complete for marketplace configuration
- All input parameters defined and validated end-to-end

## Self-Check: PASSED

All 4 files verified present. All 2 commit hashes verified in git log.

---
*Phase: 01-architecture-data-integration*
*Completed: 2026-03-14*
