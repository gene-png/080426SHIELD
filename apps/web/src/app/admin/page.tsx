import { redirect } from "next/navigation";

/**
 * The consultant console has no distinct index view — the intake queue is the
 * working landing (Navigation_Spec). `/admin` exists so signed-in admins from
 * `/` land on a real route; it forwards to the queue. Role enforcement lives in
 * the admin layout, which runs for this route too.
 */
export default function AdminIndexPage(): never {
  redirect("/admin/queue");
}
