import { useState } from "react";
import ChatPage from "./ChatPage";
import LandingPage from "./LandingPage";

function App() {
  const [showChat, setShowChat] = useState(false);

  if (showChat) {
    return (
      <>
        <div className="home-back-bar">
          <button type="button" onClick={() => setShowChat(false)}>
            ← Back to home
          </button>
        </div>

        <ChatPage />
      </>
    );
  }

  return <LandingPage onStart={() => setShowChat(true)} />;
}

export default App;