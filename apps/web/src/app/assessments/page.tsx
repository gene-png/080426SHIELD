import type { Metadata } from "next";

import { AssessmentsView } from "@/components/assessments/AssessmentsView";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";
import { SkipToContent } from "@/components/site/SkipToContent";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "My assessments",
};

export default function AssessmentsPage(): JSX.Element {
  return (
    <>
      <SkipToContent />
      <PublicHeader />
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto max-w-6xl px-6 py-10 outline-hidden"
      >
        <AssessmentsView />
      </main>
      <PublicFooter />
    </>
  );
}
