# citeable-docs

An unofficial, free "ask the docs" assistant for [VisiData](https://www.visidata.org/). It answers only from VisiData's documentation, shows a citation link for every answer, and says "not found" (with the closest pages) when the docs do not cover the question.

**Status: early work in progress.** Nothing is deployed yet. So far this repository holds the design, the implementation plan, and small measurement scripts ("spikes") that check the plan's assumptions before any product code is written.

**Not affiliated with VisiData.** This is an independent project. VisiData and its documentation are licensed under GPLv3 and belong to their authors; this repository does not contain copies of the documentation.

## Where to look
- `docs/superpowers/specs/` the design spec
- `docs/superpowers/plans/` the implementation plan (checkboxes show progress)
- `docs/decisions/decision-log.md` why each decision beat its alternatives
- `docs/spikes/` measured findings, with their caveats
- `spikes/` the scripts behind those findings

## Constraints
Everything runs on free tiers with no card. The assistant has no tools and no access to private data.

## License
Code: MIT (see `LICENSE`).
