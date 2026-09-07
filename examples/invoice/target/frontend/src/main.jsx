import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';

function Invoice() {
  const [id, setId] = useState('42');
  const [amount, setAmount] = useState('');
  const [error, setError] = useState('');
  async function load() {
    setAmount(''); setError('');
    try {
      const response = await fetch('/api/invoice?id=' + encodeURIComponent(id));
      const value = await response.json();
      if (!response.ok) setError(value.error);
      else setAmount(value.amount); // String: never coerce the decimal into Number.
    } catch { setError('Unavailable'); }
  }
  return <main>
    <h1>Invoice</h1>
    <label htmlFor="invoice-id">Invoice ID</label>
    <input id="invoice-id" value={id} onChange={event => setId(event.target.value)} />
    <button id="load" onClick={load}>Load</button>
    <p id="amount">{amount}</p>
    <p id="error" role="alert">{error}</p>
  </main>;
}
createRoot(document.getElementById('root')).render(<Invoice />);
