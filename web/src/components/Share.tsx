"use client";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import QR from "@/components/QR";

export default function Share({ path, token }: { path: string; token?: string | null }) {
  const t = useTranslations("common");
  const [url, setUrl] = useState("");
  useEffect(() => {
    setUrl(`${window.location.origin}${path}${token ? `?share_token=${token}` : ""}`);
  }, [path, token]);
  return (
    <div className="flex flex-col sm:flex-row gap-4 items-start">
      {url && <QR text={url} size={120} />}
      <div className="text-xs flex flex-col gap-2 min-w-0">
        <code className="break-all border border-rule px-2 py-1 bg-[#faf6ee]">{url}</code>
        <button type="button" className="border border-ink px-2 py-1 self-start" onClick={() => navigator.clipboard?.writeText(url)}>
          {t("copyLink")}
        </button>
      </div>
    </div>
  );
}
