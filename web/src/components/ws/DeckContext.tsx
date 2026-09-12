"use client";
import { createContext, useContext } from "react";
import type { Deck, EffectiveRole, Membership, User } from "@/lib/types";

export interface DeckCtx {
  deck: Deck;
  me: User | null;
  role: EffectiveRole;
  atLeast: (r: EffectiveRole) => boolean;
  members: Membership[] | null;
  refresh: () => void;
}
export const DeckContext = createContext<DeckCtx | null>(null);
export function useDeckCtx(): DeckCtx {
  const c = useContext(DeckContext);
  if (!c) throw new Error("useDeckCtx outside a deck workspace");
  return c;
}
