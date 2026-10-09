import './MedicineSandbox.css';
import { config } from './config';

const money = (value) => Number.isFinite(value)
  ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: config.currency }).format(value) : null;

function sourceLink(quote) {
  try {
    const url = new URL(quote.product_url || quote.search_url);
    return url.protocol === 'https:' ? url.href : undefined;
  } catch { return undefined; }
}

function Quotes({ prices, savings = [] }) {
  return <div className="pharmacy-quotes">
    {!prices?.quotes?.length && <p>{config.no_quotes}</p>}
    {prices?.quotes?.map((quote, index) => {
      const saving = savings.find((row) => row.pharmacy === quote.pharmacy
        && row.alternative_product_url === quote.product_url);
      const link = sourceLink(quote);
      return <div className="quote" key={`${quote.pharmacy}-${index}`}>
        <strong>{quote.pharmacy_name || quote.pharmacy}</strong>
        <div>{quote.status === 'ok' ? money(quote.price) || config.price_unavailable : config.price_unavailable}</div>
        {money(quote.mrp) && <small>MRP: {money(quote.mrp)}</small>}
        {quote.pack_size && <small>{quote.pack_size}</small>}
        {money(quote.unit_price) && quote.unit && <small>{money(quote.unit_price)} per {quote.unit}</small>}
        {quote.conditions?.map((condition, i) => <small key={i}>{condition}</small>)}
        {saving && Number.isFinite(saving.percent) && <small className="saving-value">
          {saving.percent}% lower per {saving.unit} at this pharmacy
        </small>}
        {link && <a href={link} target="_blank" rel="noopener noreferrer">View pharmacy</a>}
      </div>;
    })}
    {prices?.note && <p className="sandbox-note">{prices.note}</p>}
  </div>;
}

export default function MedicineSandbox({ data }) {
  const original = data.original;
  const composition = original.composition.map((row) =>
    `${row.drug}${row.strength ? ` (${row.strength})` : ''}`).join(' + ');
  return <section className="medicine-sandbox" aria-label="Medicine comparison">
    <div className="sandbox-heading"><h3>Medicine details</h3></div>
    <div className="sandbox-summary">
      <div className="summary-card"><span className="summary-label">IDENTIFIED MEDICINE</span>
        <strong>{original.medicine}</strong><small>{original.regulatory}</small></div>
      <div className="summary-card"><span className="summary-label">ACTIVE COMPOSITION</span>
        <strong>{composition || config.no_data}</strong></div>
    </div>
    <h4>Pharmacy prices</h4><Quotes prices={original.prices} />
    <h4>Listed alternatives</h4>
    {!data.alternatives.length ? <p>{config.no_alternatives}</p> :
      <div className="comparison-scroll" role="region" aria-label="Alternative medicine prices" tabIndex={0}>
        <table className="comparison-table"><thead><tr>
          <th scope="col">Alternative</th><th scope="col">Composition match</th>
          <th scope="col">Pharmacy quotes and savings</th>
        </tr></thead><tbody>{data.alternatives.map((alternative) => <tr key={alternative.medicine}>
          <td><strong>{alternative.medicine}</strong><small>{alternative.regulatory}</small></td>
          <td><span className="match-badge">{alternative.composition_match
            ? 'Ingredient and strength match in database' : 'Match not confirmed'}</span></td>
          <td><Quotes prices={alternative.prices} savings={alternative.savings} /></td>
        </tr>)}</tbody></table>
      </div>}
    <p className="sandbox-note">{data.note}</p>
  </section>;
}
