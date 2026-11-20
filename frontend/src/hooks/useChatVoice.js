import { useEffect, useRef, useState } from "react";
import { recordChatVoice } from "../api/chatVoice.js";

export function useChatVoice(enabled, language, setDraft) {
  const session = useRef(null);
  const [phase, setPhase] = useState(null);
  const [partial, setPartial] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    setPhase(null);
    setPartial("");
    setError(null);
    return () => {
      session.current?.cancel();
      session.current = null;
    };
  }, [enabled, language]);

  function toggle(draft) {
    if (!enabled || phase === "finishing") return;
    if (phase === "connecting") {
      session.current?.cancel();
      session.current = null;
      setPhase(null);
      return;
    }
    if (phase === "listening") {
      setPhase("finishing");
      session.current?.stop();
      return;
    }
    setError(null);
    setPhase("connecting");
    const reset = (message) => {
      session.current = null;
      setPhase(null);
      setPartial("");
      setError(message);
    };
    session.current = recordChatVoice({
      language,
      onListening: () => setPhase("listening"),
      onResult: (final, interim) => {
        if (final) setDraft([draft.trimEnd(), final].filter(Boolean).join(" ").slice(0, 1000));
        setPartial(interim);
      },
      onDone: (hasText) => reset(hasText ? null : "micError"),
      onError: reset,
    });
  }

  return { phase, partial, error, toggle };
}
