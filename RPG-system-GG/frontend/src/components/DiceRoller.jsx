import { useState } from 'react';
import { Dices, X } from 'lucide-react';

function rollExpression(expression) {
  const clean = expression.trim().toLowerCase().replace(/\s+/g, '');
  if (!/^[0-9d+-]+$/.test(clean)) throw new Error('Use formatos como d20, 2d6+3 ou d20-2.');
  const terms = clean.match(/[+-]?[^+-]+/g) || [];
  let total = 0;
  const details = [];
  for (const term of terms) {
    const sign = term.startsWith('-') ? -1 : 1;
    const raw = term.replace(/^[+-]/, '');
    const dice = raw.match(/^(\d*)d(\d+)$/);
    let value;
    if (dice) {
      const quantity = Number(dice[1] || 1);
      const sides = Number(dice[2]);
      if (quantity < 1 || quantity > 20 || sides < 2 || sides > 1000) throw new Error('Use dados de 1d2 a 20d1000.');
      const rolls = Array.from({ length: quantity }, () => Math.floor(Math.random() * sides) + 1);
      value = rolls.reduce((sum, roll) => sum + roll, 0);
      details.push(`${sign < 0 ? '-' : ''}[${rolls.join(', ')}]`);
    } else if (/^\d+$/.test(raw)) {
      value = Number(raw);
      details.push(`${sign < 0 ? '-' : '+'}${value}`);
    } else {
      throw new Error('Expressão inválida.');
    }
    total += sign * value;
  }
  return { total, details: details.join(' ') };
}

export default function DiceRoller({ onRoll, autor = 'Mestre' }) {
  const [open, setOpen] = useState(false);
  const [expression, setExpression] = useState('d20');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  function roll() {
    try {
      const next = { ...rollExpression(expression), expression: expression.trim() };
      setResult(next);
      onRoll?.({ ...next, autor });
      setError('');
    } catch (err) {
      setResult(null);
      setError(err.message);
    }
  }

  function rollQuick(die) {
    setExpression(die);
    try {
      const next = { ...rollExpression(die), expression: die };
      setResult(next);
      onRoll?.({ ...next, autor });
      setError('');
    } catch (err) {
      setResult(null);
      setError(err.message);
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-20">
      {!open ? (
        <button className="icon-btn h-11 w-11 border border-border bg-surface shadow-xl hover:border-accent" onClick={() => setOpen(true)} title="Rolar dados" aria-label="Rolar dados">
          <Dices className="h-5 w-5" />
        </button>
      ) : (
        <>
          <div className="fixed inset-0" onClick={() => setOpen(false)} />
          <div className="card w-64 shadow-2xl relative">
          <div className="mb-3 flex items-center justify-between">
             <h2 className="flex items-center gap-2 text-sm font-semibold"><Dices className="h-4 w-4 text-accent" /> Dados</h2>
            <button className="icon-btn h-6 w-6" onClick={() => setOpen(false)} title="Fechar rolador" aria-label="Fechar rolador"><X className="h-3.5 w-3.5" /></button>
          </div>
          <div className="mb-2 flex gap-1">
            {['d20', 'd6', 'd100'].map(die => <button key={die} className="btn-ghost btn-sm flex-1" onClick={() => rollQuick(die)}>{die}</button>)}
          </div>
          <div className="flex gap-1">
            <input className="input" value={expression} onChange={e => setExpression(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') roll(); }} aria-label="Expressão de dados" />
            <button className="btn-accent btn-sm" onClick={roll}>Rolar</button>
          </div>
          {error && <p className="mt-2 text-xs text-accent">{error}</p>}
          {result && <div className="mt-3 border-t border-border pt-3"><p className="text-3xl font-bold text-accent">{result.total}</p><p className="mt-1 text-xs text-muted">{result.details}</p></div>}
          </div>
        </>
      )}
    </div>
  );
}
