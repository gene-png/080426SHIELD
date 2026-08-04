import Link from "next/link";
import { redirect } from "next/navigation";

import { AdminShell } from "@/components/admin/AdminShell";
import { SignOutButton } from "@/components/site/SignOutButton";
import { SkipToContent } from "@/components/site/SkipToContent";
import { auth } from "@/lib/auth/options";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session) {
    redirect("/sign-in?callbackUrl=/admin/queue");
  }
  if (session.role !== "admin") {
    // Authenticated but wrong role. Navigation_Spec §6: never a bare refusal —
    // show where the user CAN go, plus a way out.
    return (
      <div className="min-h-screen bg-surface-sunken">
        <SkipToContent />
        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-16 outline-hidden"
        >
          <h1 className="text-2xl font-semibold text-ink-primary">
            Not authorized
          </h1>
          <p className="mt-2 text-ink-secondary">
            The admin console is restricted to Kentro consultants. Here&apos;s
            where you can go instead.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/assessments"
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
            >
              Go to my assessments
            </Link>
            <Link
              href="/"
              className="rounded-md border border-border bg-surface-card px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken"
            >
              Home
            </Link>
            <SignOutButton />
          </div>
        </main>
      </div>
    );
  }
  return <AdminShell email={session.user?.email}>{children}</AdminShell>;
}
