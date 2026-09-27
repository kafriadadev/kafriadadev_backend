"use server";

import { redirect } from "next/navigation";

import { ApiError, endUserSessions, grantRole, revokeGrant } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Grant, revoke, end sessions: plain form posts. Role and scope travel together, the
 * password is asked for again, and the API refuses a scoped role without its scope or a
 * scope that does not exist — this only carries the fields there.
 */
async function run(userId: string, work: (token: string) => Promise<string>): Promise<never> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const back = `/admin/users/${encodeURIComponent(userId)}`;
  try {
    const done = await work(token);
    redirect(`${back}?${new URLSearchParams({ done })}`);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`${back}?${new URLSearchParams({ error: error.message })}`);
    }
    throw error;
  }
}

const field = (formData: FormData, name: string) => String(formData.get(name) ?? "").trim();

export async function grantAction(formData: FormData): Promise<void> {
  const user = field(formData, "user");
  await run(user, async (token) => {
    const scope = field(formData, "scope_id") || field(formData, "club_id");
    await grantRole(
      token,
      user,
      field(formData, "role"),
      scope || null,
      field(formData, "reason"),
      String(formData.get("current_password") ?? ""),
      await clientMeta(),
    );
    return "granted";
  });
}

export async function revokeAction(formData: FormData): Promise<void> {
  const user = field(formData, "user");
  await run(user, async (token) => {
    await revokeGrant(
      token,
      field(formData, "grant"),
      field(formData, "reason"),
      String(formData.get("current_password") ?? ""),
      await clientMeta(),
    );
    return "revoked";
  });
}

export async function endSessionsAction(formData: FormData): Promise<void> {
  const user = field(formData, "user");
  await run(user, async (token) => {
    await endUserSessions(token, user, field(formData, "reason"), await clientMeta());
    return "sessions";
  });
}
