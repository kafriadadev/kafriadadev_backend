import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ClubFields } from "@/components/ClubFields";
import { Flash } from "@/components/Flash";
import { PageHead } from "@/components/PageHead";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, getMe, listLgas } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { registerClubAction } from "./actions";

export const metadata: Metadata = { title: "Register a club for someone" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

/**
 * Staff register a club (CLB-01's manual-entry fallback): an administrator in any
 * area, an LGA coordinator in their own. Clubs normally sign themselves up at
 * /clubs/register; anyone else who lands here is sent there.
 */
export default async function NewClubPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const me = await getMe(token).catch((e) => {
    if (e instanceof ApiError && e.status === 401) redirect("/sign-in?ended=1");
    throw e;
  });
  const isAdmin = me.roles.some((r) => r.role === "super_admin");
  const coordinator = me.roles.find((r) => r.role === "lga_coordinator");
  if (!isAdmin && !coordinator) redirect("/clubs/register");

  const get = (k: string): string => {
    const v = params[k];
    return Array.isArray(v) ? (v[0] ?? "") : (v ?? "");
  };
  const all = (k: string): string[] => {
    const v = params[k];
    return Array.isArray(v) ? v : v ? [v] : [];
  };
  const error = get("error");
  const badField = get("field");
  const duplicate = get("duplicate") === "1";

  let open: { id: string; name: string }[] = [];
  try {
    open = (await listLgas()).filter((l) => l.is_open);
  } catch {
    /* the selector is empty; the API still refuses an area that is not open */
  }

  return (
    <div>
      <PageHead
        back={{ href: "/me", label: "My account" }}
        eyebrow={isAdmin ? "Administrator" : "Coordinator"}
        title="Register a club for someone"
        lede={
          isAdmin
            ? "You become the club's administrator. Clubs normally sign themselves up."
            : `For a club in ${coordinator?.scope_name ?? "your LGA"} that cannot sign itself up. You become its administrator.`
        }
      />

      {error ? (
        <Flash
          variant={duplicate ? "warn" : "bad"}
          title={duplicate ? "This name is already used" : "We could not register the club"}
        >
          <p>
            {error}
            {duplicate ? " If yours is a different club, tick the box below and submit again." : ""}
          </p>
        </Flash>
      ) : null}

      <form action={registerClubAction} noValidate>
        <div>
          <ClubFields
            values={{ get, all }}
            badField={badField}
            error={error}
            lgas={isAdmin ? open : open.filter((l) => l.id === coordinator?.scope_id)}
          />
          {duplicate ? (
            <div>
              <label htmlFor="confirm_duplicate">
                <input id="confirm_duplicate" name="confirm_duplicate" type="checkbox" />
                This is a different club with the same name
              </label>
            </div>
          ) : null}
          <SubmitButton pending="Registering the club…">Register club</SubmitButton>
        </div>
      </form>
    </div>
  );
}
