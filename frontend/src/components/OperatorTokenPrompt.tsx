import { useState, type FormEvent } from "react";

import {
  getIngestOperatorToken,
  setIngestOperatorToken,
} from "../api/client";

interface OperatorTokenPromptProps {
  onSaved: () => void;
}

export function OperatorTokenPrompt({ onSaved }: OperatorTokenPromptProps) {
  const [token, setToken] = useState(() => getIngestOperatorToken());

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token.trim()) return;
    setIngestOperatorToken(token);
    onSaved();
  };

  return (
    <form className="operator-token-prompt" onSubmit={handleSubmit}>
      <div>
        <strong>Operator access required</strong>
        <p>
          Enter the value of <code>INGEST_OPERATOR_TOKEN</code> from Render.
          It is kept only in this browser tab.
        </p>
      </div>
      <div className="operator-token-controls">
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Ingest operator token"
          aria-label="Ingest operator token"
          autoComplete="off"
          spellCheck={false}
        />
        <button className="btn btn-primary" type="submit" disabled={!token.trim()}>
          Connect
        </button>
      </div>
    </form>
  );
}
