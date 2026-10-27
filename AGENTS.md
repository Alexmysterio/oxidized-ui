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

# Dependency policy

- Always use the latest stable versions of Python, Node.js, pnpm, Oxidized,
  Docker base images, backend dependencies, frontend dependencies and GitHub
  Actions.
- Dependabot runs daily for npm, uv, Docker and GitHub Actions. The `publish`
  workflow also rebuilds the image daily so moving `latest` base tags are
  picked up even when the repository has no new commits.
- When a new version appears, update the lockfiles, run all checks, push to
  `main` and verify the published image.
- Do not pin packages to old majors unless a newer version is incompatible;
  in that case document the reason and the upgrade blocker.
