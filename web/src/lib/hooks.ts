"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, v5 } from "./api";
import type { Deck, EffectiveRole, Membership, User } from "./types";
import { ROLE_ORDER } from "./types";

export interface Loadable<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | Error | null;
  status: number | null;
  refresh: () => void;
}

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): Loadable<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fn()
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const refresh = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, status: error instanceof ApiError ? error.status : null, refresh };
}

/** The signed-in user, a guest, or null when the API has no session for us (401). */
export function useMe(): Loadable<User> & { isGuest: boolean; signedIn: boolean } {
  const l = useLoad(() => v5.auth.me(), []);
  const me = l.status === 401 ? null : l.data;
  return { ...l, data: me, error: l.status === 401 ? null : l.error, isGuest: !!me?.is_guest, signedIn: !!me && !me.is_guest };
}

export function useDeck(slugOrId: string | null | undefined, shareToken?: string | null): Loadable<Deck> {
  return useLoad(async () => {
    if (!slugOrId) throw new ApiError(404, "no deck");
    return v5.decks.get(slugOrId, shareToken);
  }, [slugOrId, shareToken]);
}

/** Effective role of `me` in `deck`: from `deck.my_role` when the API includes it, else from the members list. */
export function useRole(deck: Deck | null, me: User | null): { role: EffectiveRole; atLeast: (r: EffectiveRole) => boolean; members: Membership[] | null } {
  const [members, setMembers] = useState<Membership[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    setMembers(null);
    if (!deck || !me || me.is_guest || deck.my_role || deck.your_role) return;
    v5.members
      .list(deck.id)
      .then((m) => {
        if (!cancelled) setMembers(m);
      })
      .catch(() => {
        if (!cancelled) setMembers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [deck?.id, me?.id, deck?.my_role, deck?.your_role, deck, me]);
  const role: EffectiveRole = useMemo(() => {
    if (!deck) return "guest";
    if (deck.your_role) return deck.your_role;
    if (deck.my_role) return deck.my_role;
    if (!me || me.is_guest) return "guest";
    if (deck.owner_id === me.id) return "owner";
    const m = members?.find((x) => x.user_id === me.id);
    if (m) return m.role;
    return "reader";
  }, [deck, me, members]);
  const atLeast = useCallback((r: EffectiveRole) => ROLE_ORDER[role] >= ROLE_ORDER[r], [role]);
  return { role, atLeast, members };
}
