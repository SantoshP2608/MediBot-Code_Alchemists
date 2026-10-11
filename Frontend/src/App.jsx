import { useState } from "react";
import ChatPage from "./ChatPage";
import LandingPage from "./LandingPage";

function App() {
  const [showChat, setShowChat] = useState(false);

  function openChat() {
    // Reset the page to the very top before opening the chat.
    window.scrollTo(0, 0);
    setShowChat(true);
  }

  function goHome() {
    window.scrollTo(0, 0);
    setShowChat(false);
  }

  if (showChat) {
    return (
      <div className="chat-page-background">
        <div className="home-back-bar">
          <button type="button" onClick={goHome}>
            Back to home
          </button>
        </div>

        <ChatPage />
      </div>
    );
  }

  return <LandingPage onStart={openChat} />;
}

export default App;