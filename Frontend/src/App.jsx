import { useEffect, useRef, useState } from "react";
import "./App.css";
import MedicineSandbox from "./MedicineSandbox";
import { sampleSandbox } from "./sampleSandbox";

const welcome = {
  role: "assistant",
  text: "Hello! I'm MediBot. Ask me about a medicine, its information, or price comparisons.",
};

function App() {
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState("");
  const [accepted, setAccepted] = useState(false);
  const messagesEnd = useRef(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(event) {
    event.preventDefault();

    const question = input.trim();
    if (!question || !accepted) return;

    setMessages((previous) => [
      ...previous,
      { role: "user", text: question },
      {
        role: "assistant",
        text: "Your message was received. Answers will appear here once the backend is connected.",
      },
    ]);

    setInput("");
  }

  function previewSandbox() {
    if (!accepted) return;

    setMessages((previous) => [
      ...previous,
      {
        role: "user",
        text: "Show me a sample medicine comparison.",
      },
      {
        role: "assistant",
        text: "Here are your details for Example Medicine 500. This comparison uses fictional sample data.",
        sandbox: sampleSandbox,
      },
    ]);
  }

  function startNewChat() {
    setMessages([welcome]);
    setInput("");
  }

  return (
    <main className="medibot">
      <header className="chat-header">
        <div className="brand">
          <img
            src="/medibot-logo.jfif"
            alt="MediBot logo"
            className="bot-logo"
          />

          <div>
            <h1>MediBot</h1>
            <p>Your medication information assistant</p>
          </div>
        </div>

        <button
          className="new-chat-button"
          type="button"
          onClick={startNewChat}
        >
          New chat
        </button>
      </header>

      <section className="disclaimer" aria-label="Medical disclaimer">
        <strong>Medical disclaimer</strong>
        <p>
          MediBot provides general information and does not replace
          professional medical advice. Consult a qualified healthcare
          professional before taking or changing medication.
        </p>

        <label>
          <input
            type="checkbox"
            checked={accepted}
            onChange={(event) => setAccepted(event.target.checked)}
          />
          I understand and acknowledge this disclaimer.
        </label>
      </section>

      <section className="chat-panel" aria-label="Medication chat">
        <div className="chat-panel-heading">
          <h2>Chat with MediBot</h2>
          <span className="preview-badge">Frontend preview</span>
        </div>

        <button
          className="sandbox-preview-button"
          type="button"
          onClick={previewSandbox}
          disabled={!accepted}
        >
          Preview sample comparison
        </button>

        <div
          className="messages"
          role="log"
          aria-label="Conversation"
          aria-live="polite"
        >
          {messages.map((message, index) => (
            <div
              className={`message-row ${message.role}`}
              key={index}
            >
              <div className="message-bubble">
                <span className="message-author">
                  {message.role === "user" ? "You" : "MediBot"}
                </span>
                <p>{message.text}</p>
                {message.role === "assistant" && message.sandbox && (
                  <MedicineSandbox data={message.sandbox} />
                )}
              </div>
            </div>
          ))}

          <div ref={messagesEnd} />
        </div>

        <form className="message-form" onSubmit={handleSubmit}>
          <input
            aria-label="Your message"
            type="text"
            placeholder={
              accepted
                ? "Type your medication question..."
                : "Acknowledge the disclaimer to start"
            }
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={!accepted}
            maxLength={2000}
          />

          <button
            type="submit"
            disabled={!accepted || !input.trim()}
          >
            Send <span aria-hidden="true">➜</span>
          </button>
        </form>

        <p className="chat-footer">
          Information only · Backend not connected yet
        </p>
      </section>
    </main>
  );
}

export default App;