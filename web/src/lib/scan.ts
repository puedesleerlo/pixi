"use client";

/** Scan a QR code with the camera (BarcodeDetector). Resolves the 4-letter code found in a /s/CODE or /r/CODE
 * link (or the raw value), or null on timeout; throws when the browser cannot scan. */
export async function scanSessionCode(timeoutMs = 20000): Promise<string | null> {
  const w = window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => { detect: (s: ImageBitmapSource) => Promise<{ rawValue: string }[]> } };
  if (!w.BarcodeDetector || !navigator.mediaDevices?.getUserMedia) throw new Error("unsupported");
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
  const video = document.createElement("video");
  video.srcObject = stream;
  await video.play();
  const det = new w.BarcodeDetector({ formats: ["qr_code"] });
  const deadline = Date.now() + timeoutMs;
  try {
    while (Date.now() < deadline) {
      const found = await det.detect(video).catch(() => []);
      if (found.length) {
        const m = found[0].rawValue.match(/\/(?:s|r)\/([A-Za-z]{4})/);
        return m ? m[1].toUpperCase() : found[0].rawValue;
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    return null;
  } finally {
    stream.getTracks().forEach((tr) => tr.stop());
  }
}
