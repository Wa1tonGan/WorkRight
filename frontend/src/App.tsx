import { useEffect, useState } from "react";
import { api, type Identity } from "./api";
import LoginPage from "./LoginPage";
import ChatPage from "./ChatPage";

export default function App() {
  // undefined = still checking the session, null = signed out
  const [identity, setIdentity] = useState<Identity | null | undefined>(undefined);

  useEffect(() => {
    api.me().then(setIdentity).catch(() => setIdentity(null));
  }, []);

  if (identity === undefined) return <div className="booting">WorkRight…</div>;
  if (identity === null) return <LoginPage onLogin={setIdentity} />;
  return (
    <ChatPage
      identity={identity}
      onLogout={async () => {
        await api.logout();
        setIdentity(null);
      }}
    />
  );
}
