// Narration for the Triadr demo, generated with ElevenLabs.
//   node vo-gen.js            all sections
//   VO_ONLY=v03 node vo-gen.js   one section
// Key and voice come from .env next to this file (never committed).
const fs = require('fs');
for (const line of fs.existsSync('.env') ? fs.readFileSync('.env', 'utf8').split('\n') : []) {
  const m = line.match(/^([A-Z_]+)=(.*)$/);
  if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim();
}
const key = process.env.ELEVENLABS_API_KEY;
if (!key) { console.error('Set ELEVENLABS_API_KEY'); process.exit(1); }
const VOICE = process.env.ELEVENLABS_VOICE || 'CwhRBWXzGAHq8TQ4Fs17';
const MODEL = 'eleven_multilingual_v2';

// Ten sections, ~112 s of speech. Every figure here is reproducible from the repo.
const SECTIONS = [
  ['00', "Triadr. A self-healing multi-app agent."],
  ['01', "Most multi-app agents are linear scripts. They break in production, because when step four of six dies, steps one to three already happened. The approval is still pending. The money already moved."],
  ['02', "Triadr takes one sentence and carries it across three external apps. GitHub audits the pull request. Telegram asks a human to approve. Stripe releases the payout."],
  ['03', "Every call passes through one reliability gate. It validates, retries, reroutes around dead endpoints, refuses to pay twice, and rolls the workflow back when a step cannot recover."],
  ['04', "This is a real run. GitHub scores the pull request fifty-two out of a hundred: medium risk, human approval required. The verdict is written back onto the commit."],
  ['05', "The card arrives in Telegram with working Approve and Reject buttons. The agent stops and waits for a person. Nothing moves until someone presses."],
  ['06', "Approved. Stripe releases twenty-five dollars to the contractor under an idempotency key derived from the workload, so replaying the run returns the same transfer instead of paying again. The receipt is posted back under the card."],
  ['07', "Now watch it fail. Three quarters of calls are rejected on first attempt. Timeouts, rate limits, dropped connections. The gate absorbs fifteen faults and still settles the payout exactly once."],
  ['08', "And when it truly cannot recover. Stripe goes down after the card is posted. Triadr retracts the card, resets the commit status, and reports honestly. No money moved."],
  ['09', "Forty runs under that storm. Three hundred and fifty-six faults absorbed. Zero runs left half-executed. Zero duplicate payouts. Forty of forty audit chains verify. Triadr. One agent, three apps, zero half-executed workflows."],
];

const only = process.env.VO_ONLY ? process.env.VO_ONLY.replace(/^v/, '') : null;
const todo = SECTIONS.filter(([id]) => !only || id === only);
console.log('characters:', todo.reduce((n, s) => n + s[1].length, 0), 'in', todo.length, 'sections');
fs.mkdirSync('vo', { recursive: true });
fs.mkdirSync('public/vo', { recursive: true });

(async () => {
  for (const [id, text] of todo) {
    const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${VOICE}`, {
      method: 'POST',
      headers: { 'xi-api-key': key, 'content-type': 'application/json', accept: 'audio/mpeg' },
      body: JSON.stringify({ text, model_id: MODEL, voice_settings: { stability: 0.5, similarity_boost: 0.8, style: 0.0, use_speaker_boost: true } }),
    });
    if (!res.ok) { console.error(id, 'FAILED', res.status, (await res.text()).slice(0, 200)); process.exit(1); }
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(`vo/v${id}.mp3`, buf);
    fs.writeFileSync(`public/vo/v${id}.mp3`, buf);
    console.log(id, 'ok', text.length, 'chars');
  }
})();
