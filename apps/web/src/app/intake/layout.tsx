import { redirect } from "next/navigation";

import { auth } from "@/lib/auth/options";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";

export default async function IntakeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session) {
    redirect("/sign-in?callbackUrl=/intake");
  }
  return (
    <>
      <PublicHeader />
      <main className="mx-auto w-full max-w-4xl px-6 py-10">
        <header className="mb-8 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
            New assessment
          </p>
          <h1 className="text-3xl font-semibold text-ink-primary">Intake</h1>
          <p className="max-w-prose text-ink-secondary">
            Tell us about your organization and the services you want assessed.
            The wizard saves after each field so you can return any time before
            submitting.
          </p>
        </header>
        {children}
      </main>
      <PublicFooter />
    </>
  );
}
