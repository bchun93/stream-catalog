import { useState, type FormEvent } from "react";

import { getAdminApiKey, setAdminApiKey } from "../api/client";

interface AdminTokenPromptProps {
  onClose: () => void;
}

export function AdminTokenPrompt({ onClose }: AdminTokenPromptProps) {
  const [token, setToken] = useState(() => getAdminApiKey());

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token.trim()) return;
    setAdminApiKey(token);
    onClose();
  };

  return (
    <div className="token-dialog-backdrop" role="presentation">
      <form
        className="token-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-token-title"
        onSubmit={handleSubmit}
      >
        <h2 id="admin-token-title">Admin access required</h2>
        <p>
          Enter the value of <code>ADMIN_API_KEY</code> from Render, then retry
          your action. It is kept only in this browser tab.
        </p>
        <input
          autoFocus
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Admin API key"
          aria-label="Admin API key"
          autoComplete="off"
          spellCheck={false}
        />
        <div className="token-dialog-actions">
          <button className="btn btn-ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" type="submit" disabled={!token.trim()}>
            Save for this tab
          </button>
        </div>
      </form>
    </div>
  );
}
