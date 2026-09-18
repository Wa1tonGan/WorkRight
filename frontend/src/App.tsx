import { useEffect, useState } from "react";
import { api, type Identity } from "./api";
import LoginPage from "./LoginPage";
import ChatPage from "./ChatPage";
import PolicyPage from "./PolicyPage";

export default function App() {
  // undefined = still checking the session, null = signed out
  const [identity, setIdentity] = useState<Identity | null | undefined>(undefined);
  const [view, setView] = useState<"chat" | "policy">("chat");

  useEffect(() => {
    api.me().then(setIdentity).catch(() => setIdentity(null));
  }, []);

  if (identity === undefined) return <div className="booting">WorkRight…</div>;
  if (identity === null) return <LoginPage onLogin={setIdentity} />;
  if (view === "policy") return <PolicyPage onBack={() => setView("chat")} />;
  return (
    <ChatPage
      identity={identity}
      onShowPolicy={() => setView("policy")}
      onLogout={async () => {
        await api.logout();
        setIdentity(null);
      }}
    />
  );
}
