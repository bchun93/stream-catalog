import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "./Button";

interface CopyButtonProps {
  value: string;
  label?: string;
}

export function CopyButton({ value, label = "Copy" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <Button
      variant="subtle"
      className="copy-btn"
      onClick={handleCopy}
      aria-label={copied ? "Copied" : label}
      icon={copied ? <Check size={14} /> : <Copy size={14} />}
    />
  );
}
