"use client";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import * as React from "react";

import type { JSX } from "react";
import { SCHEMA_REASON_PREFIX } from "@/lib/describe-save-error";

interface FieldErrors {
  email?: string;
  password?: string;
  display_name?: string;
  form?: string;
}

/**
 * THE `schema_` LITERAL IS IMPORTED FROM `lib/describe-save-error.ts` ABOVE.
 *
 * It was DECLARED here, and `SCHEMA_REASON_PREFIX` in
 * `apps/api/app/exceptions.py` still names THIS FILE in its own docstring as
 * the TS-side site — which is why this note sits here rather than only at the
 * new home. A reader sent here by the Python comment is one hop from the
 * constant, and the hop is the import at the top of this file. (Repointing the
 * Python docstring is NOT DONE HERE — `exceptions.py` is outside this PR's
 * territory — and is tracked in **#393**.
 *
 * This clause has now been wrong in BOTH directions, which is the part worth
 * keeping. It first read "is filed" while no issue existed: a status word
 * carrying no output. It was then corrected to "NOT FILED", citing
 * `gh issue list --search SCHEMA_REASON_PREFIX` returning nothing — and that
 * same search returned #393 within the hour. A search result is a measurement
 * with a timestamp, not a property, so quoting one as a standing fact about an
 * open population goes stale exactly the way a count does. Cite the number.)
 *
 * It moved because the same prefix decides the same question for every
 * client-facing surface that goes through `serverReason`, which had no guard at
 * all and was rendering "Request validation failed." to clients. A second
 * literal in this bundle would be a second place for the two to disagree.
 * Across the LANGUAGE boundary it is still duplicated, because there is no
 * build step shared by the FastAPI app and this bundle.
 *
 * BOTH DIRECTIONS ARE COVERED, and this paragraph said the opposite. It read
 * "a Python-side edit reddens NOTHING. `test_schema_422_typed_reason.py`
 * imports the constant from the module under test, so it follows any change
 * silently." That file holds
 * `test_the_schema_namespace_is_the_literal_the_web_layer_spells_out`, whose
 * body is `assert exceptions.SCHEMA_REASON_PREFIX == "schema_"` — an
 * independently spelled literal, not the imported value — and whose own
 * docstring says the gap existed "until this test existed". So a Python-side
 * edit DOES go red, in the file cited three lines earlier as proof that it does
 * not.
 *
 * Recorded rather than quietly swapped, because the sentence arrived under
 * "stated rather than left to be discovered" and that phrasing ends the check:
 * a reader who believed it would open a PR to add a cross-language pin that
 * already ships. The TS side is pinned too — `schemaReasonFallback` in
 * `SignUpForm.test.tsx` spells the literal out instead of importing it, and
 * `describe-save-error.test.ts` does the same.
 */

/**
 * Whether the envelope's `message` is fit to put in front of a person.
 *
 * Keyed on the VALUE of `reason`, never on its presence. #307 gave every
 * schema-level 422 a typed reason, which made a presence test — the shape this
 * branch used to carry — true for exactly the responses it was written to
 * exclude: the friendly fallback below became unreachable and `/sign-up`
 * rendered "Request validation failed." under the Email field (#317).
 *
 * The general shape, worth the sentence: a field added to a shared envelope is
 * additive only if no consumer branches on its PRESENCE. #307's own docstring
 * claimed "a consumer that wants the typed reason opts in", and this component
 * had already opted in by accident.
 */
function carriesUserFacingCopy(
  reason: string | undefined,
  message: string | undefined,
): message is string {
  if (!reason || !message) return false;
  return !reason.startsWith(SCHEMA_REASON_PREFIX);
}

export function SignUpForm(): JSX.Element {
  const router = useRouter();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [errors, setErrors] = React.useState<FieldErrors>({});
  const [pending, setPending] = React.useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setErrors({});
    setPending(true);

    const res = await fetch("/api/proxy/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, display_name: displayName }),
    });
    // 429 is here because the exemption that used to omit it was FALSE.
    //
    // `dashboards-render-the-typed-reason.test.ts` certified this component as
    // "NOT a live instance: every typed reason `/auth/register` can emit is a
    // 409 or 422", enumerating four reasons. `register` opens with
    // `limiter.enforce_auth(request, email)`, and `RateLimiter.check` raises a
    // typed 429 `{"reason": "rate_limited", ...}` before the handler body runs
    // -- so the throttled case fell past this gate to the untyped fallback and
    // told the user to "Try again", which re-trips the limiter it was throttled
    // by. The server's own "slow down and try again shortly" was discarded.
    //
    // The enumeration was made twice, carefully, and still missed it: both
    // passes read the handler body, and this one is raised on the line above
    // it. That is why the dispatch below is by STATUS rather than by a list of
    // reasons.
    //
    // BUT THIS IS STILL AN ENUMERATION, and "any typed envelope this endpoint
    // can produce is read" -- what this comment said -- is the failed claim in
    // a new costume: a present-tense completeness claim over a population that
    // keeps acquiring members. Re-derived 2026-09-21 by reading
    // `routes/auth.py::register` and everything it calls, the typed reasons
    // reachable here are `rate_limited` (429, from
    // `security/rate_limit.py::RateLimiter.check`), `email_exists` (409),
    // `password_policy` (422), `email_invalid` (422) and
    // `email_domain_unavailable` (409, both from
    // `_resolve_registration_tenant`), and `schema_*` (422, from
    // `_handle_validation_error`). Three statuses cover all six TODAY. Nothing
    // makes that keep being true.
    //
    // The trigger, stated so it is mechanical rather than remembered: adding a
    // typed refusal to `/auth/register` -- or to anything it calls, which is
    // where the 429 came from -- at a status outside this list reinstates the
    // defect silently. `SignUpForm.test.tsx` pins the 429 and would not notice
    // a fourth status. The structural fix is to gate on `!res.ok` and keep a
    // 5xx-specific fallback in the final `else`; not done here because it
    // changes the copy a 500 shows, which is wider than the review this came
    // from.
    if (res.status === 409 || res.status === 422 || res.status === 429) {
      // The API returns a typed error envelope: error.reason is a stable
      // machine code, error.message is human-friendly copy. Map each reason to
      // the field it belongs to so the copy lands next to the offending input
      // (and never surfaces a raw "Request validation failed.").
      // PARSE DEFENSIVELY. This was a bare `await res.json()`.
      //
      // A non-JSON body -- an edge WAF or CDN 429 with an HTML or empty body
      // (NOT this app's own proxy: `route.ts` re-wraps upstream bodies as
      // JSON, and `apiFetch` passes a bare string through as valid JSON, so
      // the throw needs an intermediary in front of Next; and NOT a 504,
      // which never enters the 409|422|429 branch this annotates)
      // -- made it throw, the async submit handler's promise rejected,
      // and `setPending(false)` below never ran. The Create account button
      // stayed disabled forever, with nothing on screen saying why, on the
      // PUBLIC sign-up page: a user who hit it could not retry without
      // reloading (#389).
      //
      // `json()` inside a `try`, NOT `text()` then `JSON.parse`. The recorded
      // rule about reading a Response body once is about an error path that
      // tries `json()` and then FALLS BACK to `text()` -- that throws "body
      // stream already read" and the TypeError replaces the error being built.
      // There is no fallback here, so one read is all that happens.
      //
      // The empty envelope is NOT a swallowed error: it routes to the `else`
      // below, which renders plain-language copy, so the user sees a message
      // and can retry. Throwing is what showed them nothing.
      let body: { error?: { message?: string; reason?: string } } = {};
      try {
        body = (await res.json()) as typeof body;
      } catch {
        body = {};
      }
      const reason = body.error?.reason;
      const message = body.error?.message;
      if (reason === "email_exists") {
        setErrors({
          email: "An account already exists for that email. Sign in instead.",
        });
      } else if (reason === "password_policy") {
        setErrors({ password: message ?? "Choose a stronger password." });
      } else if (reason === "rate_limited") {
        // FORM-level, not a field error: nothing the user typed is wrong.
        // Rendering it on the email input would be a false claim about that
        // value, and the remedy is about timing rather than input.
        setErrors({
          form:
            message ??
            "Too many attempts. Please wait a moment before trying again.",
        });
      } else if (carriesUserFacingCopy(reason, message)) {
        // Any other typed backend rejection (D-016 envelope) — e.g. the rare
        // email_domain_unavailable or email_invalid — carries friendly copy, so
        // surface it on the email field. (Self-registration is open now, so the
        // old domain-approval reasons no longer fire on the happy path.)
        setErrors({ email: message });
      } else if (res.status === 429) {
        // A THROTTLE IS STILL A THROTTLE WHEN THE BODY IS UNUSABLE.
        //
        // This case fell through to the input prompt below, which says
        // "then try again" -- advice that re-trips the limiter, and a claim
        // about what the user typed for an error that is not about their
        // input. The comment on the 429 branch above names that exact harm as
        // the reason the branch exists, and the branch then failed to cover
        // its own untyped case.
        setErrors({
          form: "Too many attempts. Please wait a moment before trying again.",
        });
      } else {
        // Nothing here is fit to render: either an untyped body, or a schema
        // refusal whose message is the internal "Request validation failed."
        // Show a plain-language prompt instead of leaking that string.
        //
        // Reached only for 409 and 422 now -- both genuinely about the
        // submitted values, which is what makes this copy true here.
        setErrors({
          form: "Please double-check your name, email, and password (12+ characters), then try again.",
        });
      }
      setPending(false);
      return;
    }
    if (!res.ok) {
      setErrors({
        form: "Something went wrong creating your account. Try again.",
      });
      setPending(false);
      return;
    }

    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });
    if (!result || result.error) {
      router.replace("/sign-in?registered=1");
      return;
    }
    // Full-page navigation so the server re-renders the header/nav with the new
    // session and the client lands on the intake form without a manual refresh.
    window.location.assign("/intake");
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="display_name"
          className="text-sm font-medium text-ink-primary"
        >
          Full name
        </label>
        <input
          id="display_name"
          type="text"
          required
          value={displayName}
          autoComplete="name"
          onChange={(e) => setDisplayName(e.target.value)}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-border-focus focus:outline-hidden"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className="text-sm font-medium text-ink-primary">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={errors.email ? "true" : undefined}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-border-focus focus:outline-hidden"
          placeholder="you@example.gov"
        />
        {errors.email ? (
          <p className="text-xs text-status-danger-fg">{errors.email}</p>
        ) : null}
      </div>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="password"
          className="text-sm font-medium text-ink-primary"
        >
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          minLength={12}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={errors.password ? "true" : undefined}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus:border-border-focus focus:outline-hidden"
        />
        <p className="text-xs text-ink-tertiary">
          12+ characters. Choose something memorable.
        </p>
        {errors.password ? (
          <p className="text-xs text-status-danger-fg">{errors.password}</p>
        ) : null}
      </div>
      {errors.form ? (
        <div
          role="alert"
          className="rounded-md border border-status-danger-border bg-status-danger-bg px-3 py-2 text-sm text-status-danger-fg"
        >
          {errors.form}
        </div>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-brand-500 px-4 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Creating account…" : "Create account"}
      </button>
    </form>
  );
}
