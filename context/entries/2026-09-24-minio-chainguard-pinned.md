# 2026-09-24: MinIO images move to Chainguard, pinned by digest

Branch `fix/minio-images-chainguard`, base `0a831a7`.

## What broke

Every E2E and Demo job, on `main` and on every open PR, died at stack start.
`quay.io/minio/mc:latest` answered 401 and `quay.io/minio/minio:latest` had
"no such manifest". This was reproduced from a dev machine, not only from the
runner. It is the second time: on 2026-09-19 the same images vanished from
Docker Hub, and compose moved to quay.io, still on `:latest`. MinIO has stopped
publishing public images. Machines that still run the stack are running
cached copies.

## The root cause is the tag, not the registry

A third-party `:latest` in CI. It let a supplier's decision break every PR at
once, with nothing in the repo changing. The fix pins what lands.

## What changed

- `minio` and `createbuckets` use `cgr.dev/chainguard/minio` and
  `cgr.dev/chainguard/minio-client`. These are free, public and unauthenticated
  (measured by pulling). Chainguard says it rebuilds them from source; that was
  not measured.
- **Pinned by digest.** The free tier offers only `latest` / `latest-dev`, so
  the digest is the pin. The server digest is MinIO
  `RELEASE.2026-09-22T19-25-18Z`. The client reports no version
  (`DEVELOPMENT.GOGET`), so its build date, 2026-09-24T03:05:08Z, identifies it.
  The compose comment's update procedure covers both images, together.
- **Retention was measured, not assumed.** A digest pin lasts only as long as
  the registry keeps the digest. Ten superseded `minio` digests, built between
  2025-10-24 and 2026-09-13, all still resolved on 2026-09-24. That is evidence,
  not a promise. If a pin stops resolving, re-pin; if it recurs, mirror.
- `-dev` variants, because the distroless images have no shell and no HTTP
  client. The healthcheck and the bucket job both need one.
- The healthcheck uses `wget`, because the image has no `curl`.
- `mailhog` is pinned by digest too (`v1.0.1`, its last release). On
  2026-09-24 `:latest` was the same manifest, so nothing that runs changes.
  It was the last third-party `:latest` in compose.
- `user: "0:0"` on `minio`. Chainguard runs as uid 65532, and a named volume
  at `/data` is created root-owned, so the server refused it ("file access
  denied", measured). Root is what the quay image ran as.

## Rejected: pinning an old quay tag

The repo owner's decision, 2026-09-24. CVE-2025-62506 was reported against
MinIO, and per the owner its maintainers declined to patch it in the containers.
Not checked here: that the pinned release contains the fix. A historical image would ship a known, unpatched
CVE into a FedRAMP-track product. The cached quay images on dev machines carry
it too. That is worth knowing, but not urgent.

## Verified

- **Fresh volume, isolated containers:**
  - the server starts;
  - `/minio/health/live` and the console on :9001 both answer;
  - `createbuckets`' exact command creates the bucket;
  - a second run of that command is idempotent.
- **This dev stack's existing volume:** `minio` is healthy, `createbuckets`
  exits 0, and the api's `/ready` reports `minio: ok`.

## Residual

- The pin is manual. `.github/dependabot.yml` has no docker ecosystem, so
  nothing proposes new digests. The compose comment says how to update one.
- Running MinIO non-root would need every existing `minio-data` volume
  migrated.
