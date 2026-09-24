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

## The root cause is the repository, and the pin fixes only the tag

**Corrected before merge.** The first version of this PR said the root cause
was "a third-party `:latest` in CI". The adversarial review challenged that,
and a measurement settled it. Both outages were REPOSITORY withdrawals. On
2026-09-24 the exact digests this dev machine had been running answered 401
from quay.io and "repository does not exist" from Docker Hub, while the same
probe got 200 from repositories known to exist. A digest pin would not have
survived either outage.

The root cause is that CI's stack start depends on a third party's public
repository staying public. The digest pin fixes a different, real defect: a
floating `:latest` let a supplier change what CI runs with no change in this
repo. Withdrawal is not closed by this PR. If Chainguard withdraws or gates
the free image, the outage repeats exactly. Only a copy this repo controls
closes that, tracked in #522.

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
- **Retention was measured for both images, not assumed.** A digest pin lasts
  only as long as the registry keeps the digest. Ten superseded digests of each
  image all still resolved on 2026-09-24. The `minio` digests were built
  2025-10-24 to 2026-09-13, and the `minio-client` digests 2025-11-06 to
  2026-09-23. That is evidence, not a promise.
- `-dev` variants, because the distroless images have no shell and no HTTP
  client. The healthcheck and the bucket job both need one.
- The healthcheck uses `wget`, because the image has no `curl`.
- `mailhog` is pinned by digest too (`v1.0.1`, its last release). On
  2026-09-24 `:latest` was the same manifest, so nothing that runs changes.
  It was the last third-party `:latest` in compose. Other floating tags remain
  (#522).
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
