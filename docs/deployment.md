# Deployment

## 1. Overview

Two workflows ship the app.

- `Deploy` (`.github/workflows/deploy.yml`) applies Terraform.
- `Build image` (`.github/workflows/build-image.yml`) builds container images.

Production runs the image tag set in `terraform/production.auto.tfvars`.

```
Run "Build image" → approve → image :<sha> + :latest pushed → release PR opened
  → review + merge → "Deploy" starts → approve → container runs :<sha>
```

## 2. Image tags

- `:<sha>` is the full commit SHA. It is immutable. It is the only kind of tag production should run. The workflow refuses to overwrite one.
- `:latest` always points at the newest workflow build, or at a local `build_container.sh` build. Use it for testing. Production does not use it.
- `image_tag` in `terraform/production.auto.tfvars` is the source of truth for what is live. The git history of that line is the release history.

Bootstrap: `image_tag` is `"latest"` until the first release. The first run of `Build image` replaces it with a SHA.

## 3. Release a new version

1. Merge your code to `main`.
2. Start the build:
   `gh workflow run build-image.yml --repo WaffiAltaher/candidates_database --ref main`
   (or use Actions → Build image → Run workflow on `main`).
3. Approve the run in the GitHub UI. It uses the `production` environment.
4. The run tests the code, builds the image, pushes `:<sha>` and `:latest`, and opens a release PR.
5. Review and merge the release PR.
6. Merging starts `Deploy`. Approve it. It also uses the `production` environment.
7. Terraform rolls the container to the new image.

Close the release PR to skip a release.

## 4. Roll back

Revert the release PR's commit on `main`, or open a PR that sets `image_tag` to an older SHA that still exists in the registry. Merge it and approve the `Deploy` run.

## 5. Infrastructure-only changes

A push to `main` that changes `terraform/**` or `deploy.yml` starts `Deploy`. These changes keep the same `image_tag`, so they never change the running code. A merge that changes only app code does not start `Deploy`.

## 6. Safety checks

- `Deploy` refuses a tag that is not in the registry.
- `Build image` refuses to overwrite a SHA tag.
- `Build image` runs only from `main`.
- Tests run before the build, on Python 3.11 (the same version as the production image).
- `Deploy` still stops if the plan deletes a resource (see `CLAUDE.md`).

## 7. Local builds

`bash terraform/build_container.sh [tag]` builds and pushes a test image. The default tag is `latest`. The script refuses 40-character commit-SHA tags. It does not deploy anything.

## 8. One-time repository setting

Enable Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests". Without it, the PR step of `Build image` fails.

## 9. Cleaning up old images

Do this by hand, in the Scaleway console or with `scw registry`. Never delete the tag currently in `terraform/production.auto.tfvars`. Keep a few recent SHA tags for rollback.
