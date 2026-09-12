"use client";
import { useParams } from "next/navigation";
import GrammarView from "@/components/GrammarView";

export default function DeckGrammarPage() {
  const params = useParams<{ code: string }>();
  const code = (params?.code ?? "PLAY").toString().toUpperCase();
  return <GrammarView deckCode={code} />;
}
