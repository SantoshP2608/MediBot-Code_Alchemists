import { useEffect, useRef, useState } from "react";
import "./App.css";
import ResponseMessage from "./components/ResponseMessage";
import { sendMessage } from "./api/chat";
import { config } from "./config";
import LatticeLoader from "./components/LatticeLoader";

const welcome = {
  id: "welcome",
  role: "assistant",
  text: config.welcome,
};

function ChatPage() {
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const messagesEnd = useRef(null);
  const session = useRef(null);
  const generation = useRef(0);
  const inflight = useRef(null);
  const activeOffer = useRef(null);

  useEffect(() => {
    const container = messagesEnd.current?.parentElement;

    if (container && (messages.length > 1 || loading)) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, loading]);

  useEffect(() => () => {
    generation.current += 1;
    inflight.current?.abort();
  }, []);

  async function ask(question, requestId, retryId, selection = null) {
    if (inflight.current) return;
    if (!session.current) session.current = crypto.randomUUID();
    const currentGeneration = generation.current;
    const controller = new AbortController();
    inflight.current = controller;
    activeOffer.current = null;
    setLoading(true);
    setMessages((previous) => retryId ? previous.filter((item) => item.id !== retryId)
      : [...previous, { id: requestId, role: 'user', text: question }]);
    try {
      const payload = selection
        ? { ...selection, session_id: session.current, request_id: requestId }
        : { message: question, session_id: session.current, request_id: requestId };
      const body = await sendMessage(payload, controller.signal, selection ? 'select' : 'chat');
      if (currentGeneration !== generation.current) return;
      session.current = body.session_id;
      const result = body.result;
      activeOffer.current = result.action === 'clarify' ? result.selection_offer || null : null;
      setMessages((previous) => [...previous, {
        id: crypto.randomUUID(), role: 'assistant',
        result, retry: result.action === 'error' ? { question, requestId, selection } : null
      }]);
    } catch (error) {
      if (currentGeneration !== generation.current || controller.signal.aborted) return;
      setMessages((previous) => [...previous, {
        id: crypto.randomUUID(), role: 'assistant',
        text: error.message, retry: { question, requestId, selection }
      }]);
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

  const inputRef = useRef(null);

  useEffect(() => {
    if (!loading && accepted) {
      inputRef.current?.focus({ preventScroll: true });
    }
  }, [loading, accepted]);

  useEffect(() => {
    const textarea = inputRef.current;
    if (!textarea) return;

    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    textarea.style.overflowY =
      textarea.scrollHeight > 160 ? "auto" : "hidden";
  }, [input]);

  function startNewChat() {
    generation.current += 1;
    inflight.current?.abort();
    inflight.current = null;
    session.current = crypto.randomUUID();
    activeOffer.current = null;
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
            alt=""
            className="bot-logo"
          />

          <div>
            <img
              src="/medibot-title.png"
              alt="MediBot"
              className="chat-wordmark"
            />
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

      <section
        className="disclaimer chitti-disclaimer"
        aria-label="Medical disclaimer"
      >
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
            onClick={(event) => {
              event.stopPropagation();
            }}
          />
          I understand and acknowledge this disclaimer.
        </label>
      </section>

      <section
        className="chat-panel chitti-panel"
        aria-label="Medication chat"
      >
        <div className="chat-panel-heading chitti-panel-heading">
          <h2>Chat with Chitti</h2>
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
                <div className="message-sender">
                  {message.role === "assistant" && (
                    <img
                      src="/medibot-logo.png"
                      alt=""
                      className="chitti-avatar"
                    />
                  )}

                  <strong className="message-author">
                    {message.role === "user" ? "You" : "Chitti"}
                  </strong>
                </div>

                {message.text && <p>{message.text}</p>}
                {message.result && <ResponseMessage result={message.result}
                  choicesDisabled={loading || !accepted || activeOffer.current !== message.result.selection_offer}
                  onSelect={(item, offer) => {
                    if (offer !== activeOffer.current) return;
                    ask(item.name, crypto.randomUUID(), null,
                      { product_id: item.product_id, selection_offer: offer });
                  }} />}
                {message.retry && <button className="retry-button" type="button"
                  disabled={loading || !accepted}
                  onClick={() => ask(message.retry.question, message.retry.requestId, message.id, message.retry.selection)}>
                  Retry
                </button>}
              </div>
            </div>
          ))}

          {loading && (
            <div className="chat-thinking">
              <LatticeLoader
                status="working"
                label="Thinking"
                doneLabel="Done in"
                errorLabel="Failed after"
                pattern="orbit"
                grid={3}
                shape="round"
                doneColor="#22c55e"
                errorColor="#ef4444"
                cellSize={6}
                gap={2}
                fontSize={14}
                step={90}
                idleOpacity={0.15}
                glow={false}
                glowColor=""
                showTimer
                color="#f5f5f5"
              />
            </div>
          )}
          <div ref={messagesEnd} />
        </div>

        <form className="message-form" onSubmit={handleSubmit}>
          <textarea
            aria-label="Your message"
            ref={inputRef}
            rows={1}
            placeholder={
              accepted
                ? "Type your question... Click Enter to send"
                : "Acknowledge the disclaimer to start"
            }
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            disabled={!accepted || loading}
            maxLength={config.maxMessageLength}
          />

          <button
            type="submit"
            disabled={!accepted || loading || !input.trim()}
          >
            Send
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="19"
              height="19"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z" />
              <path d="m21.854 2.147-10.94 10.939" />
            </svg>
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
