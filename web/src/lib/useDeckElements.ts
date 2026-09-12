"use client";
import { useEffect, useState } from "react";
import { api, Element, LibraryGroup } from "./api";

const cache = new Map<string, Promise<LibraryGroup[]>>();

/** The picker contents for a deck (placeable elements of its enabled libraries), fetched once per page load. */
export function useDeckElements(deckCode: string | null) {
  const [groups, setGroups] = useState<LibraryGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!deckCode) return;
    let alive = true;
    if (!cache.has(deckCode)) cache.set(deckCode, api.deckElements(deckCode));
    cache
      .get(deckCode)!
      .then((g) => alive && setGroups(g))
      .catch((e) => {
        cache.delete(deckCode);
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [deckCode]);
  const byId = new Map<string, Element>();
  for (const g of groups ?? []) for (const e of g.elements) byId.set(e.id, e);
  return { groups, byId, error };
}
