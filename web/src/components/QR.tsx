"use client";
import { useEffect, useState } from "react";
import QRCode from "qrcode";

export default function QR({ text, size = 200 }: { text: string; size?: number }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    QRCode.toDataURL(text, {
      width: size,
      margin: 1,
      color: { dark: "#141414", light: "#f4efe6" },
      errorCorrectionLevel: "M",
    })
      .then((u) => alive && setUrl(u))
      .catch(() => alive && setUrl(null));
    return () => {
      alive = false;
    };
  }, [text, size]);
  if (!url) return <div style={{ width: size, height: size }} className="border border-rule" />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} width={size} height={size} alt={`QR code for ${text}`} className="border border-rule" />;
}
