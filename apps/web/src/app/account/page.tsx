import type { Metadata } from "next";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import { MfaEnrollment } from "@/components/auth/MfaEnrollment";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";
import { SignOutButton } from "@/components/site/SignOutButton";
import { SkipToContent } from "@/components/site/SkipToContent";
import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

import type { JSX } from "react";

interface MeResponse {
  mfa_enrolled: boolean;
}

/** Read the signed-in user's MFA state; default to "not enrolled" if the
 * lookup fails so the account page still renders the enable flow. */
async function fetchMfaEnrolled(bearer: string | undefined): Promise<boolean> {
  if (!bearer) {
    return false;
  }
  try {
    const me = await apiFetch<MeResponse>("/auth/me", { bearer, clientId: "" });
    return Boolean(me.mfa_enrolled);
  } catch (err) {
    if (err instanceof ApiError) {
      return false;
    }
    throw err;
  }
}

export const metadata: Metadata = { title: "Account" };

function Row({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border-subtle py-2 last:border-0">
      <span className="text-sm font-medium text-ink-secondary">{label}</span>
      <span className="text-sm text-ink-primary">{value}</span>
    </div>
  );
}

export default async function AccountPage(): Promise<JSX.Element> {
  const session = await auth();
  const role = session?.role ?? "—";
  const mfaEnrolled = await fetchMfaEnrolled(session?.accessToken);
  return (
    <>
      <SkipToContent />
      <PublicHeader />
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-10 outline-hidden"
      >
        <div>
          <h1 className="text-2xl font-semibold text-ink-primary">Account</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Your SHIELD profile and session.
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
          </CardHeader>
          <CardBody className="flex flex-col gap-1">
            <Row label="Email" value={session?.user?.email ?? "—"} />
            <Row label="Role" value={role} />
            <div className="pt-4">
              <SignOutButton />
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Two-factor authentication</CardTitle>
          </CardHeader>
          <CardBody>
            <MfaEnrollment initiallyEnrolled={mfaEnrolled} />
          </CardBody>
        </Card>
      </main>
      <PublicFooter />
    </>
  );
}
