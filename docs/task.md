# Insider Activity Scanner - Task Tracker

## Planning
- [x] Create implementation plan with architecture, modules, and data sources
- [x] Get user approval on the plan

## Execution
- [x] Set up project structure and dependencies
- [x] Build stock universe module (market cap rank 210-500)
- [x] Build price/volume scanner module (2:30 PM IST check)
- [x] Build news checker module (verify if news exists for flagged stocks)
- [ ] Build sector-relative check module (deferred to v2)
- [x] Build main orchestrator and output/report generator
- [x] Add scheduling/automation capability

## Verification
- [x] Test each module individually with sample data
- [x] Run end-to-end scan and validate output
- [x] Create walkthrough

## Feedback Applied
- [x] Install deps for Python 3.11 (user's actual interpreter)
- [x] Raise MIN_PCT_CHANGE from 2% to 4% (Indian market volatility)
- [x] Rewrite news module: analyze headlines for catalyst vs generic mentions
- [x] Re-test end-to-end pipeline with updated logic
