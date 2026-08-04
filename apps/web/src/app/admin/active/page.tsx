import { redirect } from "next/navigation";

/**
 * Issue 6: /admin/active was a stub whose entire body was a paragraph and a
 * "Go to the intake queue" button — a link that led nowhere new, which is the
 * dead end Navigation_Spec §12 forbids. The nav entry now points straight at
 * the queue.
 *
 * The route survives as a redirect rather than a 404 so existing bookmarks and
 * any deep link still land somewhere useful. The original page is preserved
 * under "Review for Deletion/" pending sign-off.
 */
export default function ActiveWorkPage(): never {
  redirect("/admin/queue");
}
