import { useEffect, useRef, useState } from "react";
import "./App.css";
import ResponseMessage from "./components/ResponseMessage";
import { sendMessage } from "./api/chat";
import { config } from "./config";

const welcome = { id: 'welcome', role: 'assistant', text: config.welcome };

function ChatPage() {
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const messagesEnd = useRef(null);
  const session = useRef(null);
  const generation = useRef(0);
  const inflight = useRef(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => () => {
    generation.current += 1;
    inflight.current?.abort();
  }, []);

  async function ask(question, requestId, retryId) {
    if (inflight.current) return;
    if (!session.current) session.current = crypto.randomUUID();
    const currentGeneration = generation.current;
    const controller = new AbortController();
    inflight.current = controller;
    setLoading(true);
    setMessages((previous) => retryId ? previous.filter((item) => item.id !== retryId)
      : [...previous, { id: requestId, role: 'user', text: question }]);
    try {
      const body = await sendMessage({ message: question, session_id: session.current,
        request_id: requestId }, controller.signal);
      if (currentGeneration !== generation.current) return;
      session.current = body.session_id;
      const result = body.result;
      if (!(result.action === 'block' && result.reason === 'schedule_x')) {
        setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'assistant',
          result, retry: result.action === 'error' ? { question, requestId } : null }]);
      }
    } catch (error) {
      if (currentGeneration !== generation.current || controller.signal.aborted) return;
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'assistant',
        text: error.message, retry: { question, requestId } }]);
    } finally {
      if (currentGeneration === generation.current) {
        inflight.current = null;
        setLoading(false);
      }
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    const question = input.trim();
    if (!question || !accepted || inflight.current) return;
    setInput("");
    ask(question, crypto.randomUUID());
  }

  function startNewChat() {
    generation.current += 1;
    inflight.current?.abort();
    inflight.current = null;
    session.current = crypto.randomUUID();
    setLoading(false);
    setMessages([welcome]);
    setInput("");
  }

  return (
    <main className="medibot">
      <header className="chat-header">
        <div className="brand">
          <img
            src="/medibot-logo.png"
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

        </div>

        <div
          className="messages"
          role="log"
          aria-label="Conversation"
          aria-live="polite"
        >
          {messages.map((message) => (
            <div
              className={`message-row ${message.role}`}
              key={message.id}
            >
              <div className="message-bubble">
                <span className="message-author">
                  {message.role === "user" ? "You" : "MediBot"}
                </span>
                {message.text && <p>{message.text}</p>}
                {message.result && <ResponseMessage result={message.result} />}
                {message.retry && <button className="retry-button" type="button"
                  disabled={loading || !accepted}
                  onClick={() => ask(message.retry.question, message.retry.requestId, message.id)}>
                  Retry
                </button>}
              </div>
            </div>
          ))}

          {loading && <p className="loading-message" role="status">{config.loading}</p>}
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
            disabled={!accepted || loading}
            maxLength={config.maxMessageLength}
          />

          <button
            type="submit"
            disabled={!accepted || loading || !input.trim()}
          >
            Send <span aria-hidden="true">➜</span>
          </button>
        </form>

        <p className="chat-footer">
          Information only · Check prices at the pharmacy before purchasing
        </p>
      </section>
    </main>
  );
}

export default ChatPage;
