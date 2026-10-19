import MedicineSandbox from '../MedicineSandbox';
import { config } from '../config';
import SplitText from './SplitText';
import MedicineChoices from './MedicineChoices';

export default function ResponseMessage({ result, onSelect, choicesDisabled = true }) {
  const shown = new Set();
  return <>
    {result.disclaimer && <p className="response-disclaimer" role="note"><SplitText text={result.disclaimer} /></p>}
    {result.message && <p><SplitText text={result.message} /></p>}
    {result.medicine_choices?.length > 0 && <MedicineChoices items={result.medicine_choices}
      offer={result.selection_offer} disabled={choicesDisabled} onSelect={onSelect} />}
    {!result.medicine_choices?.length && result.candidates?.length > 0 && <ul>{result.candidates.map((item, index) =>
      <li key={index}>{typeof item === 'string' ? item : item.name}</li>)}</ul>}
    {result.results?.map((item, index) => {
      if (item.status !== 'ok') return <p key={index}><SplitText text={item.message || config.no_data} /></p>;
      if (['price_comparison', 'alternative_search'].includes(item.intent)) {
        return item.data.map((comparison) => {
          if (shown.has(comparison.original.medicine)) return null;
          shown.add(comparison.original.medicine);
          return <MedicineSandbox key={comparison.original.medicine} data={comparison} />;
        });
      }
      if (item.intent === 'general_health') return <p key={index}><SplitText text={item.data} /></p>;
      const field = item.intent === 'side_effects' ? 'side_effects' : 'uses';
      return <section key={index} className="medicine-information">
        <h3>{field === 'side_effects' ? 'Side effects' : 'Uses'}</h3>
        {item.data.map((medicine, medicineIndex) => <div key={medicineIndex}>
          <strong>{medicine.medicine}</strong>
          {medicine[field]?.length ? <ul>{medicine[field].map((text, i) => <li key={i}><SplitText text={text} /></li>)}</ul>
            : <p><SplitText text={config.no_data} /></p>}
        </div>)}
      </section>;
    })}
  </>;
}
