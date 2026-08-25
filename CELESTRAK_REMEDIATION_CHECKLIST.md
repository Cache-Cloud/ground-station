# CelesTrak remediation checklist

## Purpose

This checklist records the remediation required after CelesTrak placed a
Ground Station IP address in its firewall on 2026-04-28. The reported causes
were repeated HTTP errors, non-canonical domains, retired queries, legacy TLE
requests, and continued requests after failure.

The implementation must comply with the [CelesTrak usage policy](https://celestrak.org/usage-policy.php)
and [GP data query documentation](https://celestrak.org/NORAD/documentation/gp-data-formats.php).

## Current implementation status (2026-08-25)

- [x] Migrate known historical CelesTrak defaults to canonical GP/CSV URLs;
  disable unknown historical CelesTrak URLs for explicit user review.
- [x] Use OMM/GP as the canonical stored orbit representation. Retain a derived
  TLE cache only where the catalogue number and downstream consumer support it.
- [x] Persist per-source sync telemetry for **all** providers: last successful
  sync, last attempt, HTTP status, and latest error. CelesTrak suspension and
  the two-hour query interval remain CelesTrak-only safeguards.
- [x] Show each source's status, error details, and humanized last successful
  sync in the Sources UI. A successful CelesTrak source is shown as Healthy
  even when its next request is deferred by the two-hour interval.
- [x] Refresh the Sources UI after every terminal sync outcome, including a
  failed or partially completed synchronization.
- [ ] Add the remaining automated migration, circuit-breaker, HTTP-status, and
  six-digit runtime-boundary regression coverage listed below before release.

## Required behavior

- [x] Send CelesTrak requests only to `https://celestrak.org`.
- [ ] Build GP requests from documented queries and current documented group
  names. Do not use legacy static `.txt` feeds.
- [x] Request GP data explicitly as `FORMAT=CSV`. CelesTrak's GP documentation
  lists CSV as a supported format and its usage policy directs clients to move
  from legacy formats to CSV.
- [x] Do not request TLE/3LE/2LE from CelesTrak.
- [ ] Fetch only configured data that the user will use. Deduplicate identical
  CelesTrak requests within a synchronization run.
- [x] Persist the time of each successful CelesTrak request and do not repeat a
  GP query more often than once every two hours, including manual syncs and
  restarts.
- [x] Treat **only HTTP 200** as a successful CelesTrak response.
- [x] Disable automatic redirect following for CelesTrak requests so a 301 is
  visible to the application rather than hidden by the HTTP client.
- [x] On any CelesTrak non-200 response (including 301, 403, 404, and 5xx),
  immediately stop all further CelesTrak requests for that run.
- [x] Persist a clear human-action-required error containing the source URL,
  HTTP status, response summary, and time. Do not automatically retry that
  source or claim a successful synchronization.

## Findings and implementation tasks

### 1. Redirects are currently hidden

Status: complete (2026-08-25)

`requests.get()` follows redirects by default in
`backend/tlesync/source_adapters.py`. A `www.celestrak.*` request can therefore
generate a 301 at CelesTrak while the application sees only a later response.

- [x] Introduce one CelesTrak request helper used by every CelesTrak adapter.
- [x] Set `allow_redirects=False` in that helper.
- [x] Reject any status other than 200 before parsing a response body.
- [x] Include the status code and CelesTrak response text (safely truncated) in
  the reported error.
- [ ] Extend the regression test from 301 to 403, 404, and 5xx responses,
  proving that parsing is
  not attempted and no follow-up CelesTrak request is made.

### 2. A failed source currently does not stop later source requests

Status: complete (2026-08-25; multi-source regression test still pending)

`synchronize_satellite_data_internal()` records a fetch exception and continues
to the next source. Several CelesTrak sources can therefore multiply one bad
configuration into multiple policy-violating requests. Its final state can also
be overwritten to `success=True`, and the background worker reports completion
as successful.

- [x] Add a CelesTrak circuit breaker scoped to the sync run.
- [x] After the first CelesTrak request failure, skip every remaining CelesTrak
  source and batch in that run.
- [x] Keep non-CelesTrak sources independent if that is safe, but never issue a
  second CelesTrak request after the failure.
- [x] Preserve failure state through task completion; do not overwrite it with
  a successful database-processing result.
- [x] Present the error prominently in the sync UI and task result as requiring
  human investigation.
- [ ] Add integration tests with multiple CelesTrak sources to prove that one
  non-200 response produces exactly one CelesTrak HTTP request.

### 3. Existing users have not been migrated

Status: complete (2026-08-25; migration coverage remains to be automated)

The current migration that mentions CelesTrak only normalizes the provider
label. It does not migrate URLs, groups, formats, adapters, or existing TLE
configuration. Newer defaults do not repair databases created by earlier
releases.

- [x] Add an Alembic migration after the current head that operates on
  `orbital_sources`.
- [x] Map every known first-start default and known legacy Ground Station URL to
  its canonical `https://celestrak.org/NORAD/elements/gp.php?...&FORMAT=CSV`
  equivalent.
- [x] Update each migrated source's adapter and stored format so metadata
  accurately describes the CSV/OMM-compatible response.
- [x] Do not guess replacements for arbitrary custom, static, or retired
  queries. Disable those sources and persist a migration note that tells the
  user to choose a supported source.
- [x] Normalize known bad hosts such as `www.celestrak.com` and
  `www.celestrak.org`; never preserve them as active CelesTrak URLs.
- [ ] Add migration tests covering old static `.txt` URLs, `FORMAT=tle`,
  non-canonical domains, valid documented GP group URLs, and unknown custom
  CelesTrak URLs.

### 4. New defaults use `FORMAT=omm`, not a documented format value

Status: complete (2026-08-25)

The default source URLs in `backend/server/firsttime.py` use `FORMAT=omm`.
CelesTrak currently responds with CSV because CSV is the default, but `OMM` is
the data model rather than a documented GP `FORMAT` value. The source metadata
also calls this `format=omm`, obscuring the actual wire format.

- [x] Change default CelesTrak URLs to explicit `FORMAT=CSV`.
- [ ] Model CSV as a supported source transport format, or clearly name the
  existing adapter as an OMM-compatible CSV parser.
- [ ] Keep XML and JSON parsing only where a configured provider explicitly
  returns those documented formats.
- [ ] Update source-editor labels, help text, and tests so users do not select
  undocumented CelesTrak query formats.

### 5. The runtime still requires TLE compatibility data

Status: in progress (2026-08-25)

The initial GP/OMM parser converted every record back to TLE, and the OMM
propagator required those generated lines. This fails for catalogue IDs above
99999 because TLE has only a five-character catalogue-number field.

- [x] Keep the immediate remediation separate from this larger migration:
  CelesTrak stops receiving TLE requests independently of runtime work.
- [x] Inventory TLE consumers: tracking, pass prediction, Doppler, frontend
  payloads, export/import paths, and SatDump integration.
- [x] Store canonical OMM payloads in `satellite_orbits`; retain a derived TLE
  cache only for five-digit catalogue IDs and allow the legacy
  `satellites.tle1/tle2` cache to be absent through an Alembic migration.
- [x] Initialize SGP4/Skyfield propagation directly from the canonical OMM
  payload in the orbit service.
- [x] Move tracker details, map position/path, and pass prediction to the orbit
  service's OMM-capable Skyfield construction path.
- [ ] Move or explicitly preserve the remaining TLE-only boundaries: hardware
  Doppler/rig control and any export or downstream integration that still
  requires TLE-compatible lines.
- [ ] Retain derived TLE/Alpha-5 only where a downstream dependency explicitly
  supports it, and document that compatibility boundary.
- [ ] Add six-digit NORAD fixtures to API, tracking, and export paths.
- [x] Add six-digit NORAD fixtures to GP import, canonical storage, and the
  orbit-service propagation boundary.

### 6. Rate limiting and source selection need policy controls

Status: partially complete (2026-08-25)

The scheduled sync is every 24 hours, which is within CelesTrak's two-hour GP
update cadence. Manual sync has no persistent rate limit, however, and the
source editor accepts arbitrary HTTP(S) URLs.

- [x] Enforce the two-hour CelesTrak query interval persistently, not only with
  an in-memory lock.
- [ ] Prevent the first startup sync and a manual sync from issuing duplicate
  requests for the same query.
- [ ] Add a dedicated CelesTrak source type with a URL builder and allowlisted
  current groups instead of accepting arbitrary CelesTrak URLs as generic HTTP
  sources.
- [x] Keep a generic HTTP source type for non-CelesTrak providers.
- [x] Add a user-facing warning when an existing CelesTrak source is disabled
  by migration or by a non-200 response.

## Verification before release

- [ ] Run the full backend unit test suite, including the new request, circuit
  breaker, migration, and six-digit-catalog fixtures.
- [ ] Test an upgrade from a database created by each affected release.
- [x] Inspect the upgraded `orbital_sources` table and confirm that no enabled
  CelesTrak URL has a `www` host, a static `.txt` path, a TLE format request,
  or an undocumented format value.
- [ ] Verify that a 301, 403, 404, and 5xx each stop further CelesTrak traffic
  and create a persistent human-action-required status.
- [ ] Verify that repeated manual sync actions do not repeat a successful GP
  request inside the two-hour interval.
- [x] Verify a clean installation uses only canonical, documented CelesTrak
  GP/CSV URLs.
- [ ] Prepare a short remediation summary for CelesTrak describing the URL
  migration, exact-200 handling, immediate stop behavior, and two-hour limit.
