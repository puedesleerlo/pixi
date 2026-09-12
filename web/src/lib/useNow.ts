"use client";
import { useEffect, useState } from "react";

/** Re-renders every `everyMs`; returns Date.now(). Used for countdowns. */
export function useNow(everyMs = 250) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(t);
  }, [everyMs]);
  return now;
}
