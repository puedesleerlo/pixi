"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { DeckRole } from "@/lib/types";

export default function MembersPage() {
  const t = useTranslations("members");
  const { deck, atLeast, role } = useDeckCtx();
  const members = useLoad(() => v5.members.list(deck.id), [deck.id]);
  const invitations = useLoad(async () => (atLeast("curator") ? v5.members.invitations(deck.id) : []), [deck.id, atLeast]);
  const [email, setEmail] = useState("");
  const [invRole, setInvRole] = useState<DeckRole>("member");
  const [link, setLink] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      {members.error && <ErrorState error={members.error} status={members.status} />}
      <table className="text-sm w-full">
        <thead className="text-[10px] uppercase tracking-wider text-muted text-left">
          <tr>
            <th className="py-1">{t("member")}</th>
            <th className="py-1">{t("role")}</th>
            <th className="py-1">{t("joined")}</th>
            {role === "owner" && <th />}
          </tr>
        </thead>
        <tbody>
          {members.data?.map((m) => (
            <tr key={m.id} className="border-t border-rule">
              <td className="py-2">{m.user?.name ?? m.user_id}</td>
              <td className="py-2">
                {role === "owner" && m.role !== "owner" ? (
                  <select value={m.role} onChange={(e) => v5.members.update(deck.id, m.user_id, { role: e.target.value as DeckRole }).then(members.refresh)} className="border border-rule bg-transparent text-xs">
                    <option value="member">member</option>
                    <option value="curator">curator</option>
                  </select>
                ) : (
                  m.role
                )}
              </td>
              <td className="py-2 text-muted text-xs">{m.joined_at?.slice(0, 10)}</td>
              {role === "owner" && (
                <td className="py-2 text-right">
                  {m.role !== "owner" && (
                    <button type="button" className="text-xs underline" onClick={() => v5.members.update(deck.id, m.user_id, { remove: true }).then(members.refresh)}>
                      {t("remove")}
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {atLeast("curator") && (
        <section className="border border-rule p-4 flex flex-col gap-2 text-sm">
          <div className="font-display text-lg">{t("invite")}</div>
          <div className="flex gap-2">
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="border border-rule px-2 py-1.5 flex-1" placeholder="email" />
            <select value={invRole} onChange={(e) => setInvRole(e.target.value as DeckRole)} className="border border-rule bg-transparent px-1">
              <option value="member">member</option>
              <option value="curator">curator</option>
            </select>
            <button type="button" className="bg-ink text-paper px-3" onClick={() => v5.members.invite(deck.id, { email, role: invRole }).then(() => (setEmail(""), invitations.refresh()))}>
              {t("send")}
            </button>
          </div>
          <button type="button" className="self-start border border-ink px-3 py-1.5 text-xs" onClick={() => v5.members.invite(deck.id, { role: invRole, link: true }).then((i) => setLink(`${window.location.origin}/invite/${i.link_token}`))}>
            {t("makeLink")}
          </button>
          {link && <code className="text-xs break-all border border-rule px-2 py-1 bg-[#faf6ee]">{link}</code>}
          {invitations.data && invitations.data.length > 0 && (
            <ul className="text-xs text-muted mt-2">
              {invitations.data.map((i) => (
                <li key={i.id}>
                  {i.email ?? t("linkInvite")} · {i.role} · {i.accepted_at ? t("accepted") : t("pending")}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
