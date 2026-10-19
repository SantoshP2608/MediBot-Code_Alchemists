import "./LandingPage.css";

function LandingPage({ onStart }) {
  return <main className="landing-picture-page" aria-label="MediBot home">
    <div className="landing-picture">
      <img
        src="/medibot-smarter-medicine.png"
        alt="MediBot. Your smart medicine assistant. Clear Answers for Healthier Days. Learn about medicines, compare prices, explore alternatives, and get guidance with MediBot."
        width="1672"
        height="941"
        fetchPriority="high"
      />
      <button className="landing-picture-start" type="button" onClick={onStart}
        aria-label="Get Started">
        <span className="landing-picture-sr">Get Started</span>
      </button>
    </div>
  </main>;
}

export default LandingPage;
