# Third-Party Notices

This project incorporates code and content from third-party sources. The list
below acknowledges those sources and documents the licensing posture for each.

---

## External skills (referenced / integrated — NOT vendored)

> [!IMPORTANT]
> **Some of these external skills are governed by PROPRIETARY (closed-source)
> licenses.** They are integrated at runtime — installed separately by the
> operator and invoked by this framework — but their source is **not** copied
> into this repository. This repository's Elastic License 2.0 grant (see
> [`LICENSE`](LICENSE)) covers **only** the code in this repo and does **NOT**
> extend to any of the external skills listed below. Before redistributing,
> bundling, or commercially using any of these skills, you **must** consult and
> comply with each skill's own license terms — open-source terms cannot be
> assumed.

This framework calls the following skills as external dependencies (they live
under `Universal-skills/skills/` and/or are installed into the agent runtime,
e.g. `summarizing-meetings`, `transcript-fetcher`, `html`, `pdf`, `docx`).
Integration points: the `summarizing-meetings` REASON harness behind
`wiki-import`, and the `transcript-fetcher` / `html` / `pdf`
fetch+convert wrappers (ADR-001, ARCHITECTURE.md §2.3).

- **Licensing posture**: **varies per skill — some are proprietary**, others are
  open-source. There is no blanket license across this skill set. Treat each as
  an independently-licensed third-party component.
- **No grant by this repo**: nothing in this repository, including its
  Elastic License 2.0, conveys any right to use, copy, modify, or redistribute
  these external skills. Their respective owners reserve all rights not granted
  by their own licenses.
- **Operator responsibility**: the operator who installs and runs these skills
  is responsible for holding a valid license to each one. This repository
  references them by contract/API only and ships none of their source.
