import type { Metadata } from "next";
import Link from "next/link";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";
import { SkipToContent } from "@/components/site/SkipToContent";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Messages" };

export default function MessagesPage(): JSX.Element {
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
          <h1 className="text-2xl font-semibold text-ink-primary">Messages</h1>
          <p className="mt-1 text-sm text-ink-secondary">
            Conversations with your SHIELD analyst are organised by assessment.
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Where to find your messages</CardTitle>
          </CardHeader>
          <CardBody className="flex flex-col items-start gap-3">
            <p className="text-sm text-ink-secondary">
              Each assessment carries its own thread, so requests for more
              information stay attached to the work they concern. Open an
              assessment to read and reply.
            </p>
            <Link
              href="/assessments"
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
            >
              Go to My Assessments
            </Link>
          </CardBody>
        </Card>
      </main>
      <PublicFooter />
    </>
  );
}
