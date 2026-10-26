# Project workflow

- Every change must be committed and pushed to `main`.
- Every push to `main` must publish the Docker image. The `publish` workflow builds and pushes
  `ghcr.io/alexmysterio/oxidized-ui:latest`; verify that the workflow succeeds before considering
  the task finished.
- Run the relevant checks before committing:
  - backend: `pytest` and `ruff check app tests`
  - frontend: `pnpm test`, `pnpm typecheck`, `pnpm lint:i18n`, `pnpm build`
  - compose: `docker compose config --quiet` (both compose files)
- Keep unrelated working-tree changes out of the commit.
