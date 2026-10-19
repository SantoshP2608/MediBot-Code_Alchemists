import ShinyText from './ShinyText';
import './MedicineChoices.css';

function productForm(name) {
  return name.match(/\b(oral suspension|oral solution|tablet|capsule|syrup|suspension|injection|drops|cream|gel|ointment)\b/i)?.[0] || '';
}

export default function MedicineChoices({ items, offer, disabled, onSelect }) {
  return <div className="medicine-choices" role="group" aria-label="Choose an exact medicine product">
    {items.map((item) => {
      const form = productForm(item.name);
      const liquid = /syrup|suspension|solution|drops/i.test(form);
      const strength = [...new Set(item.composition?.map((part) => part.strength).filter(Boolean))].join(' + ');
      return <button type="button" className="medicine-choice" key={item.product_id}
        disabled={disabled} onClick={() => onSelect?.(item, offer)}>
        <span className={`medicine-choice-icon ${liquid ? 'is-liquid' : ''}`} aria-hidden="true">
          <span className={liquid ? 'choice-bottle' : form.toLowerCase() === 'tablet' ? 'choice-tablet' : 'choice-cross'} />
        </span>
        <span className="medicine-choice-content">
          <strong className="medicine-choice-name"><ShinyText>{item.name}</ShinyText></strong>
          <span className="medicine-choice-composition">{item.composition?.map((ingredient) =>
            `${ingredient.drug} ${ingredient.strength || ''}`.trim()).join(' + ')}</span>
          <span className="medicine-choice-badges">
            {strength && <span className="choice-badge choice-strength">{strength}</span>}
            {form && <span className={`choice-badge choice-form ${liquid ? 'is-liquid' : ''} ${/syrup/i.test(form) ? 'is-syrup' : ''}`}>{form}</span>}
            {item.combination && <span className="choice-badge combination-label">Combination product</span>}
          </span>
        </span>
        <svg className="medicine-choice-arrow" width="18" height="24" viewBox="0 0 18 24" fill="none" aria-hidden="true">
          <path d="m6 5 6 7-6 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>;
    })}
  </div>;
}
