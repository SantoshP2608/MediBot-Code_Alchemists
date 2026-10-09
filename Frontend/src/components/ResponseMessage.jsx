import MedicineSandbox from '../MedicineSandbox';
import { config } from '../config';

export default function ResponseMessage({ result }) {
  if (result.action === 'block' && result.reason === 'schedule_x') return null;
  const shown = new Set();
  return <>
    {result.disclaimer && <p className="response-disclaimer" role="note">{result.disclaimer}</p>}
    {result.message && <p>{result.message}</p>}
    {result.candidates?.length > 0 && <ul>{result.candidates.map((item, index) =>
      <li key={index}>{typeof item === 'string' ? item : item.name}</li>)}</ul>}
    {result.results?.map((item, index) => {
      if (item.status !== 'ok') return <p key={index}>{item.message || config.no_data}</p>;
      if (['price_comparison', 'alternative_search'].includes(item.intent)) {
        return item.data.map((comparison) => {
          if (shown.has(comparison.original.medicine)) return null;
          shown.add(comparison.original.medicine);
          return <MedicineSandbox key={comparison.original.medicine} data={comparison} />;
        });
      }
      if (item.intent === 'general_health') return <p key={index}>{item.data}</p>;
      const field = item.intent === 'side_effects' ? 'side_effects' : 'uses';
      return <section key={index} className="medicine-information">
        <h3>{field === 'side_effects' ? 'Side effects' : 'Uses'}</h3>
        {item.data.map((medicine, medicineIndex) => <div key={medicineIndex}>
          <strong>{medicine.medicine}</strong>
          {medicine[field]?.length ? <ul>{medicine[field].map((text, i) => <li key={i}>{text}</li>)}</ul>
            : <p>{config.no_data}</p>}
        </div>)}
      </section>;
    })}
  </>;
}
