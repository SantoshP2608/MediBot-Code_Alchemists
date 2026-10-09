import "./LandingPage.css";

function LandingPage({ onStart }) {
    return (
        <div className="landing-page">
            <div className="landing-top">
                <header className="landing-nav">
                    <a
                        className="landing-brand"
                        href="#home"
                        aria-label="MediBot home"
                    >
                        <img
                            className="nav-logo"
                            src="/medibot-logo.png"
                            alt=""
                        />

                        <img
                            className="nav-wordmark"
                            src="/medibot-title.png"
                            alt="MediBot"
                        />
                    </a>

                    <div className="nav-actions">
                        <button
                            className="nav-signin"
                            type="button"
                            onClick={() => window.alert("Sign in is coming soon.")}
                        >
                            Sign In
                        </button>

                        <button
                            className="nav-start"
                            type="button"
                            onClick={onStart}
                        >
                            Get Started
                        </button>
                    </div>
                </header>

                <main className="landing-content" id="home">
                    <section className="hero-section">
                        <div className="hero-text">
                            <span className="hero-badge">
                                ✦ Your AI Medication Assistant
                            </span>

                            <h1>
                                Get Medicine
                                <br />
                                Information
                                <br />
                                <span>In One Conversation</span>
                            </h1>

                            <p>
                                Ask about medicines, explore uses and side effects,
                                compare prices, and understand your options—all in
                                one easy-to-use conversation.
                            </p>

                            <button
                                className="hero-ask-button"
                                type="button"
                                onClick={onStart}
                            >
                                Ask a Question <span aria-hidden="true">→</span>
                            </button>
                            <div className="hero-highlights">
                                <div className="hero-highlight">
                                    <img src="/Trusted.png" alt="" />
                                    <span>Trusted<br />Information</span>
                                </div>

                                <div className="hero-highlight">
                                    <img src="/Instant.png" alt="" />
                                    <span>Instant<br />Answers</span>
                                </div>

                                <div className="hero-highlight">
                                    <img src="/Price.png" alt="" />
                                    <span>Price<br />Comparison</span>
                                </div>

                                <div className="hero-highlight">
                                    <img src="/Understand.png" alt="" />
                                    <span>Easy to<br />Understand</span>
                                </div>
                            </div>
                        </div>

                    </section>
                </main>
            </div>
            <section className="home-features" aria-labelledby="features-heading">
                <h2 id="features-heading">Everything You Need in One Place</h2>

                <div className="home-feature-grid">
                    <article className="home-image-card">
                        <img
                            src="/Medicine-Information.png"
                            alt="Medicine Information: uses, dosage, side effects, precautions and more."
                        />
                    </article>

                    <article className="home-image-card">
                        <img
                            src="/Price-Comparision.png"
                            alt="Price Comparison: compare prices across pharmacies and find the best deals."
                        />
                    </article>

                    <article className="home-image-card">
                        <img
                            src="/Alternatives.png"
                            alt="Alternatives and Suggestions: get generic options and similar medicines."
                        />
                    </article>

                    <article className="home-image-card">
                        <img
                            src="/Health-Guidance.png"
                            alt="Health Guidance: general health tips and awareness information."
                        />
                    </article>
                </div>

                <p className="home-medical-note">
                    MediBot provides general information and does not replace
                    professional medical advice, diagnosis, or treatment.
                </p>
            </section>
        </div>
    );
}

export default LandingPage;