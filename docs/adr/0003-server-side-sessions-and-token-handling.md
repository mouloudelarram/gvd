# ADR 0003 â€” Server-side sessions and GitHub token handling

- Status: Proposed
- Date: 2026-07-16
- Related: F-03, F-05, F-06 (audit)

## Context

After OAuth, the code stores the GitHub access token directly in Flask's default session, which is
a **signed but not encrypted client-side cookie** (`session["access_token"] = token`). The token
is therefore transmitted to and stored in the browser. The token is also embedded in the
`git clone` URL argv in the worker path, exposing it to process listings.

## Decision

- Move to **server-side sessions** (Flask-Session backed by Redis). The cookie carries only an
  opaque session id (`Secure`, `HttpOnly`, `SameSite=Lax`).
- Store the GitHub access token **server-side only**, encrypted at rest (app-managed key from the
  secret manager). Never serialize it into any cookie, URL, log, exception, or report.
- **Rotate the session id after successful authentication** and enforce idle + absolute timeouts.
- In the worker, provide the token to git via **`GIT_ASKPASS`/credential helper or
  `http.extraHeader`**, never in argv. Keep token redaction in error output as defense in depth.

## Rationale

- Removes the token from the client entirely, satisfying "never expose access tokens through
  URLs, logs, exceptions, reports, or process listings" and "rotate sessions after
  authentication."
- Redis is already introduced by ADR 0002, so no new dependency.

## Consequences

- A session-encryption key becomes a managed secret (documented in the env catalog).
- Logout and session expiry must purge the server-side record.
- Tests must cover: token never present in rendered pages/cookies; session id rotates on login;
  cross-user report access is rejected (F-06).

## Alternatives considered

- **Encrypt the token inside the cookie:** still ships ciphertext + token lifetime to the client;
  larger attack surface than server-side storage. Rejected.
- **PKCE:** GitHub's OAuth web application flow does not use PKCE (confidential client with
  secret); not applicable. `state` validation is retained and already uses constant-time compare.
