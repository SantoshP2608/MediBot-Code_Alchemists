import "./MedicineSandbox.css";

function MedicineSandbox({ data }) {
  return (
    <section className="medicine-sandbox" aria-label="Medicine comparison">
      <div className="sandbox-heading">
        <h3>Medicine details</h3>
        {data.isDemo && <span className="demo-label">Sample data</span>}
      </div>

      <div className="sandbox-summary">
        <div className="summary-card">
          <span className="summary-label">IDENTIFIED MEDICINE</span>
          <strong>{data.name}</strong>
          <small>{data.category}</small>
        </div>

        <div className="summary-card">
          <span className="summary-label">ACTIVE COMPOSITION</span>
          <strong>{data.composition}</strong>
          <small>Base MRP: ₹{data.baseMrp.toFixed(2)}</small>
        </div>

        <div className="summary-card savings-card">
          <span className="summary-label">MAX POTENTIAL SAVINGS</span>
          <strong>{data.maxSavings}%</strong>
          <small>{data.alternatives.length} listed alternative(s)</small>
        </div>
      </div>

      <div
        className="comparison-scroll"
        role="region"
        aria-label="Alternative medicine prices"
        tabIndex={0}
      >
        <table className="comparison-table">
          <thead>
            <tr>
              <th scope="col">Suggested alternative</th>
              <th scope="col">Composition match</th>
              <th scope="col">MRP & savings</th>
              <th scope="col">Pharmacy quotes</th>
            </tr>
          </thead>

          <tbody>
            {data.alternatives.map((alternative) => (
              <tr key={alternative.id}>
                <td>
                  <strong>{alternative.name}</strong>
                  <small>{alternative.manufacturer}</small>
                </td>

                <td>
                  <span className="match-badge">
                    {alternative.matchLabel}
                  </span>
                </td>

                <td>
                  <strong>₹{alternative.mrp.toFixed(2)}</strong>
                  <small className="saving-value">
                    {alternative.savings}% savings
                  </small>
                </td>

                <td>
                  <div className="pharmacy-quotes">
                    {alternative.quotes.map((quote) => (
                      <span className="quote" key={quote.pharmacy}>
                        {quote.pharmacy}: ₹{quote.price.toFixed(2)}
                        <small>{quote.delivery}</small>
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="sandbox-note">
        {data.isDemo
          ? "Fictional prices for UI demonstration only. These are not verified medicine recommendations."
          : "Confirm any medication substitution with a qualified doctor or pharmacist."}
      </p>
    </section>
  );
}

export default MedicineSandbox;