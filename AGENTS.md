# AGENTS.md — Development Guidelines

## Branching Strategy

- **All changes must be done in a `dev` branch.**
- The `dev` branch is **NEVER** to be pushed to `origin`.
- When development is finished, changes must be **merged into the `master` branch**.
- The `master` branch is then **pushed to `origin`**.

## Design Documents

All development is governed by a design document.

- Design documents are titled `<subdirectory>-design.md`, placed in the corresponding subdirectory.
  - Example: `frontend/frontend-design.md`, `backend/backend-design.md`.
- Design documents have a **version** consisting of `major.minor`:
  - **Major** is bumped for new features.
  - **Minor** is bumped for changes or corrections.

## Application Versioning

Each application has a **version number** consisting of `major.minor.subminor`:

- **Major** and **minor** always correspond to the design document's version (`major.minor`).
- **Subminor** is used for bug fixes and small changes that do not require modification of the design document.

## Thinking

- Do not loop
- If confused stop and ask for clarity

## Issues

- Issues are managed with the "gh issue" commands.
- They must be logged with appropriate labels e.g. bug,enhancement,frontend,backend,deye-cloud.
