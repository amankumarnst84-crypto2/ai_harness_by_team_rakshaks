const $ = (selector) => document.querySelector(selector);
const all = (selector) => [...document.querySelectorAll(selector)];
const state = { config: null, runs: [], selected: null, job: null, active: null, view: 'workspace', tab: 'conversation', signature: '', busy: false };
const numbers = new Intl.NumberFormat('en');
const icons = () => window.lucide?.createIcons();
const statuses = { running: 'Running', verified_candidate: 'Verified fix', tests_pass_candidate: 'Tests pass', unverified_candidate: 'Unverified', incomplete: 'Incomplete', cancelled: 'Cancelled', error: 'Error', interrupted: 'Interrupted' };
function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}
function notice(message) { $('#notice').textContent = message; $('#notice').hidden = !message; }
async function api(path, data) {
  const options = data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Harness-Token': state.config.csrf }, body: JSON.stringify(data) };
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
function view(name) {
  state.view = name;
  all('.view').forEach(node => node.hidden = node.id !== name);
  all('.nav').forEach(node => { node.classList.toggle('active', node.dataset.view === name); node.setAttribute('aria-label', node.textContent.trim()); });
  $('#page-label').textContent = { workspace: 'Workspace', history: 'Run history', monitoring: 'Monitoring', comparison: 'Comparison' }[name];
  if (name === 'monitoring') metrics();
  if (name === 'workspace') drawContext();
}
function tab(name) {
  state.tab = name;
  all('.tab-panel').forEach(node => node.hidden = node.id !== name);
  all('.tab').forEach(node => { node.classList.toggle('active', node.dataset.tab === name); node.setAttribute('aria-selected', String(node.dataset.tab === name)); });
  if (name === 'context') drawContext();
}
function controls() {
  const model = $('#mode').value === 'model';
  $('#repo').disabled = !model || Boolean(state.active);
  $('#test').disabled = !model || Boolean(state.active);
  $('#issue').readOnly = !model || Boolean(state.active);
  $('#mode').disabled = Boolean(state.active);
  $('#run-button').disabled = Boolean(state.active) || !state.config || (model && !state.config.model_available) || state.busy;
  $('#run-button span').textContent = state.active ? 'Run in progress' : model ? 'Start debugging' : 'Run fixture';
  $('#cancel').disabled = !state.active;
  $('#connect-model').disabled = Boolean(state.active) || !state.config;
  $('#repo-note').textContent = model ? 'Clean Git repository required' : 'Disposable invoice fixture';
  if (!model && state.config) $('#test').value = JSON.stringify([state.config.python, 'check.py']);
  const label = element('span', 'tag ' + (model ? 'green' : 'amber'), model ? 'AI MODEL' : 'SIMULATION');
  $('#provider-state').replaceChildren(label, element('span', '', model ? state.config?.model || 'Not configured' : 'Fixed invoice repair · real tests'));
  $('#model-caption').textContent = state.config?.model_available ? 'Configured: ' + state.config.model : 'AI model not configured';
  $('#follow-form').hidden = !state.job || state.job.mode !== 'model' || Boolean(state.active);
  $('#stat-budget').textContent = numbers.format(state.job?.report?.token_budget || Number($('#tokens').value)) + ' budget';
}
function message(author, body, kind = '', stamp = '') {
  const article = element('article', 'message ' + kind);
  const heading = element('div', 'message-author', author);
  if (stamp) heading.append(element('small', '', stamp));
  article.append(heading, element('p', '', body));
  return article;
}
function renderJob(job) {
  state.job = job;
  const report = job.report || {};
  const events = job.events || [];
  const latest = events[events.length - 1];
  $('#run-id').textContent = job.id;
  $('#result-title').textContent = job.mode === 'demo' ? 'Fixture simulation' : 'AI session';
  $('#run-status').textContent = statuses[job.status] || job.status;
  $('#run-status').className = 'status ' + (job.status === 'running' ? 'running' : ['verified_candidate', 'tests_pass_candidate'].includes(job.status) ? 'success' : 'failure');
  const contexts = events.filter(e => e.event === 'context');
  const currentTokens = report.estimated_tokens ?? [...events].reverse().find(e => e.estimated_tokens)?.estimated_tokens;
  $('#stat-tokens').textContent = currentTokens === undefined ? '—' : numbers.format(currentTokens);
  $('#stat-reduction').textContent = report.context_reduction_percent === undefined ? '—' : report.context_reduction_percent + '%';
  $('#stat-checks').textContent = report.verification ? report.verification.charAt(0).toUpperCase() + report.verification.slice(1) : 'Running';
  $('#stat-baseline').textContent = report.baseline_verification ? 'Baseline: ' + report.baseline_verification : 'Awaiting test result';
  $('#stat-time').textContent = (report.elapsed_seconds ?? latest?.elapsed_seconds ?? 0).toFixed(1) + 's';
  $('#stat-attempts').textContent = (report.model_calls ?? events.filter(e => e.event === 'model_started').length) + ' model calls';
  const fingerprint = job.id + ':' + events.length + ':' + job.status;
  if (state.signature !== fingerprint) {
    state.signature = fingerprint;
    const conversation = $('#conversation');
    const nearBottom = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 100;
    const messages = [message(job.mode === 'demo' ? 'Fixture issue' : 'You', job.issue)];
    if (job.mode === 'demo') messages.push(message('Simulation', 'The model response is predetermined. Git edits and verification commands run for real.', 'event'));
    for (const event of events) {
      const stamp = event.elapsed_seconds.toFixed(1) + 's';
      if (event.event === 'plan') messages.push(message(job.mode === 'demo' ? 'Fixture response' : 'AI Harness', event.plan || 'No diagnosis supplied.', '', stamp));
      if (event.event === 'context') messages.push(message('Context selected', `${event.indexed_files} indexed files · ${numbers.format(event.selected_context_tokens_estimate)} estimated context tokens`, 'event', stamp));
      if (event.event === 'test') messages.push(message(event.phase === 'baseline' ? 'Baseline verification' : 'Candidate verification', event.verification === 'passed' ? 'Verification command passed.' : `Verification command failed${event.result.reason ? ': ' + event.result.reason : '.'}`, 'event', stamp));
      if (event.event === 'read') messages.push(message('AI requested context', event.requests.map(r => `${r.path}:${r.start_line || 1}-${r.end_line || 80}`).join('\n'), 'event', stamp));
      if (['edit_rejected', 'response_rejected', 'stopped'].includes(event.event)) messages.push(message('Run evidence', event.detail, 'error', stamp));
    }
    if (job.status !== 'running') {
      const good = ['verified_candidate', 'tests_pass_candidate'].includes(job.status);
      const conclusion = job.status === 'verified_candidate' ? 'The baseline failed and the candidate passed the verification command. The patch is ready for review.' : job.status === 'tests_pass_candidate' ? 'The candidate passed, but the baseline also passed. The reported bug was not reproduced by this command.' : report.error || 'This candidate has not been verified.';
      messages.push(message(statuses[job.status] || job.status, conclusion, good ? 'success' : 'error'));
    }
    conversation.replaceChildren(...messages);
    if (nearBottom) conversation.scrollTop = conversation.scrollHeight;
    const patchLines = (job.patch || '').split('\n');
    $('#diff').replaceChildren(...(job.patch ? patchLines.map(line => element('span', 'diff-line ' + (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@') || line.startsWith('diff ') ? 'meta' : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'remove' : ''), line)) : [document.createTextNode('No source changes.')]));
    const changed = patchLines.filter(line => line.startsWith('diff --git')).length;
    $('#patch-count').textContent = changed;
    $('#patch-label').textContent = changed ? `${changed} changed file${changed === 1 ? '' : 's'}` : 'No patch yet';
    $('#download-patch').hidden = !job.patch;
    $('#download-patch').href = `/api/runs/${job.id}/patch`;
    const tests = events.filter(e => e.event === 'test').map(event => {
      const block = element('div', 'test-block');
      block.append(element('h3', '', `${event.phase === 'baseline' ? 'Baseline' : 'Candidate'} / ${event.verification.toUpperCase()}`));
      block.append(element('pre', '', `${event.result.stdout || ''}${event.result.stderr || ''}\nExit ${event.result.code}${event.result.reason ? ' / ' + event.result.reason : ''}`));
      return block;
    });
    $('#test-results').className = tests.length ? '' : 'evidence-empty';
    $('#test-results').replaceChildren(...(tests.length ? tests : [document.createTextNode('No test evidence yet.')]));
    $('#context-details').className = contexts.length ? '' : 'evidence-empty';
    $('#context-details').replaceChildren(...(contexts.length ? contexts.map(event => {
      const row = element('div', 'context-row');
      row.append(element('strong', '', `Attempt ${event.attempt} · ${event.indexed_files} indexed files`));
      row.append(element('p', '', [...new Set(event.paths)].join('\n')));
      row.append(element('span', '', `${event.index_cache_hits} index cache hits · ${event.skipped_files} files excluded`));
      return row;
    }) : [document.createTextNode('No context selected yet.')]));
    $('#artifact-links').replaceChildren();
    if (job.report) for (const name of ['report', 'trace']) {
      const link = element('a', '', name === 'report' ? 'Report JSON' : 'Trace JSONL');
      link.href = `/api/runs/${job.id}/${name}`; link.download = name === 'report' ? 'report.json' : 'trace.jsonl';
      $('#artifact-links').append(link);
    }
  }
  controls(); drawContext();
}
function drawContext() {
  if (state.view !== 'workspace' || state.tab !== 'context') return;
  const canvas = $('#context-chart');
  const width = canvas.clientWidth;
  if (!width) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio); canvas.height = 170 * ratio;
  const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio);
  const events = state.job?.events?.filter(e => e.event === 'context') || [];
  const full = events.reduce((sum, e) => sum + e.eligible_full_source_tokens_estimate, 0);
  const selected = events.reduce((sum, e) => sum + e.selected_context_tokens_estimate, 0);
  ctx.font = '11px -apple-system, sans-serif';
  if (!events.length) { ctx.fillStyle = '#87978b'; ctx.fillText('No source context measurements yet.', 20, 80); return; }
  const maximum = Math.max(full, selected, 1);
  [{ label: 'Eligible full source', value: full, color: '#d1dad4' }, { label: 'Selected context', value: selected, color: '#428861' }].forEach((row, i) => {
    const y = 26 + i * 68;
    ctx.fillStyle = '#6c7a70'; ctx.fillText(`${row.label} · ${numbers.format(row.value)} est. tokens`, 20, y);
    ctx.fillStyle = '#f0f4f1'; ctx.fillRect(20, y + 12, width - 40, 20);
    ctx.fillStyle = row.color; ctx.fillRect(20, y + 12, Math.max(2, (width - 40) * row.value / maximum), 20);
  });
}
function history() {
  $('#run-count').textContent = state.runs.length;
  $('#history-empty').hidden = Boolean(state.runs.length);
  $('#history-rows').replaceChildren(...state.runs.map(job => {
    const row = element('tr');
    const info = element('td'); info.append(element('strong', '', job.issue), element('small', 'mono', job.id + ' · ' + new Date(job.created).toLocaleString()));
    row.append(info, element('td', '', job.mode === 'demo' ? 'Simulation' : job.model || job.report?.model || 'AI model'), element('td', '', statuses[job.status] || job.status), element('td', '', numbers.format(job.report?.estimated_tokens || 0)), element('td', '', job.report?.elapsed_seconds === undefined ? '—' : job.report.elapsed_seconds.toFixed(1) + 's'));
    const action = element('td'); const button = element('button', 'icon-button'); button.setAttribute('aria-label', 'Open run ' + job.id); button.title = 'Open run';
    const icon = element('i'); icon.dataset.lucide = 'arrow-up-right'; button.append(icon);
    button.addEventListener('click', () => { state.selected = job.id; state.signature = ''; view('workspace'); refresh(); });
    action.append(button); row.append(action); return row;
  }));
  icons();
}
async function metrics() {
  try {
    const response = await fetch('/metrics');
    if (!response.ok) throw new Error('Metrics unavailable');
    $('#metrics-preview').textContent = await response.text();
    $('#metrics-summary').textContent = `${state.runs.length} recorded runs · ${state.active ? '1 active' : 'No active runs'}`;
  } catch (error) { notice(error.message); }
}
async function refresh() {
  try {
    const data = await api('/api/runs');
    state.runs = data.runs; state.active = data.active;
    if (!state.selected) state.selected = data.active || data.runs[0]?.id;
    history();
    if (state.selected) renderJob(await api('/api/runs/' + state.selected));
    controls(); $('#connection').textContent = 'Local server connected';
    if (state.view === 'monitoring') await metrics();
  } catch (error) { $('#connection').textContent = 'Connection unavailable'; notice(error.message); }
}
async function start(event) {
  event.preventDefault(); notice(''); state.busy = true; controls();
  try {
    const mode = $('#mode').value;
    const body = { mode, issue: $('#issue').value, tokens: Number($('#tokens').value), attempts: Number($('#attempts').value) };
    if (mode === 'model') { body.repo = $('#repo').value.trim(); body.test = JSON.parse($('#test').value); }
    const result = await api('/api/runs', body);
    state.selected = result.id; state.signature = ''; tab('conversation'); await refresh();
  } catch (error) { notice(error.message); }
  finally { state.busy = false; controls(); }
}
all('.nav').forEach(button => button.addEventListener('click', () => view(button.dataset.view)));
all('.tab').forEach(button => button.addEventListener('click', () => tab(button.dataset.tab)));
$('#run-form').addEventListener('submit', start);
$('#refresh').addEventListener('click', refresh);
$('#mode').addEventListener('change', () => {
  if ($('#mode').value === 'model') { $('#issue').value = ''; $('#issue').placeholder = 'Describe the bug, expected behavior, and reproduction details…'; }
  else $('#issue').value = 'Fix invoice_total: a percentage discount must reduce the subtotal before tax is applied.';
  controls();
});
$('#tokens').addEventListener('input', () => { $('#budget-range').value = Math.min(30000, Number($('#tokens').value)); controls(); });
$('#budget-range').addEventListener('input', () => { $('#tokens').value = $('#budget-range').value; controls(); });
$('#cancel').addEventListener('click', async () => {
  if (!state.active) return;
  try { await api(`/api/runs/${state.active}/cancel`, {}); notice('Stopping the active run…'); await refresh(); }
  catch (error) { notice(error.message); }
});
$('#follow-form').addEventListener('submit', async event => {
  event.preventDefault();
  const follow = $('#follow-text').value.trim();
  if (!follow || !state.job) return;
  $('#mode').value = 'model'; $('#repo').value = state.job.repo; $('#test').value = JSON.stringify(state.job.test);
  $('#issue').value = state.job.issue + '\n\nAdditional requirement: ' + follow;
  controls(); await start(event); if (!$('#notice').textContent) $('#follow-text').value = '';
});
window.addEventListener('resize', drawContext);
const connectionValues = () => ({ provider: $('#provider').value, api_base: $('#api-base').value.trim(), api_key: $('#api-key').value, model: $('#model-id').value.trim() });
$('#connect-model').addEventListener('click', () => {
  if (!state.config) return;
  $('#provider').value = state.config.provider || 'groq';
  $('#api-base').value = state.config.api_base || 'https://api.groq.com/openai/v1';
  $('#model-id').value = state.config.model_available && state.config.model !== 'Custom adapter' ? state.config.model : '';
  $('#api-key').value = '';
  $('#api-key').placeholder = state.config.has_key ? 'Keep current key for this endpoint' : 'Provider API key';
  $('#connection-feedback').textContent = 'API credentials are sent only to the configured endpoint.';
  $('#connection-feedback').className = 'connection-feedback';
  $('#disconnect-model').disabled = !state.config.model_available;
  $('#connection-dialog').showModal();
});
function closeConnection() { $('#api-key').value = ''; $('#connection-dialog').close(); }
$('#close-connection').addEventListener('click', closeConnection);
$('#connection-dialog').addEventListener('cancel', () => { $('#api-key').value = ''; });
$('#provider').addEventListener('change', () => {
  $('#api-base').value = { groq: 'https://api.groq.com/openai/v1', deepseek: 'https://api.deepseek.com', qwen: '', compatible: '' }[$('#provider').value];
  $('#api-base').placeholder = $('#provider').value === 'qwen' ? 'Your regional Model Studio API base URL' : 'https://college.example/v1';
  $('#api-key').value = ''; $('#model-id').value = ''; $('#model-options').replaceChildren();
  $('#api-key').placeholder = 'Provider API key';
});
$('#load-models').addEventListener('click', async () => {
  $('#load-models').disabled = true;
  $('#connection-feedback').textContent = 'Loading model IDs…';
  try {
    const result = await api('/api/models', connectionValues());
    $('#model-options').replaceChildren(...result.models.map(id => { const option = element('option'); option.value = id; return option; }));
    $('#connection-feedback').textContent = `${result.models.length} model IDs available. Choose the exact evaluation model.`;
    $('#connection-feedback').className = 'connection-feedback';
    $('#model-id').focus();
  } catch (error) { $('#connection-feedback').textContent = error.message; $('#connection-feedback').className = 'connection-feedback error'; }
  finally { $('#load-models').disabled = false; }
});
$('#connection-form').addEventListener('submit', async event => {
  event.preventDefault(); $('#save-connection').disabled = true;
  try {
    state.config = await api('/api/connection', connectionValues());
    closeConnection(); $('#mode').value = 'model';
    $('#issue').value = ''; $('#issue').placeholder = 'Describe the bug, expected behavior, and reproduction details…';
    $('#test').value = '["python3", "-m", "pytest", "-q"]';
    controls(); notice('Model configured. API generation will be tested when you start a debugging run.');
  } catch (error) { $('#connection-feedback').textContent = error.message; $('#connection-feedback').className = 'connection-feedback error'; }
  finally { $('#save-connection').disabled = false; }
});
$('#disconnect-model').addEventListener('click', async () => {
  try { state.config = await api('/api/connection', { disconnect: true }); closeConnection(); controls(); notice('Model disconnected.'); }
  catch (error) { $('#connection-feedback').textContent = error.message; }
});
async function init() {
  icons(); view('workspace');
  try { state.config = await api('/api/config'); controls(); await refresh(); }
  catch (error) { notice(error.message); }
  async function poll() { await refresh(); setTimeout(poll, state.active ? 700 : 3500); }
  setTimeout(poll, 2000);
}
init();
