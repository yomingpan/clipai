import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

class Element {
  constructor(value = '') {
    this.value = value; this.textContent = ''; this.innerHTML = ''; this.className = '';
    this.disabled = false; this.listeners = {}; this.style = {}; this.dataset = {};
  }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  replaceChildren(...children) { this.children = children; }
  querySelector() { return new Element(); }
  append() {}
  click() { this.listeners.click?.({ target: this }); }
}

class PhraseRejectingRecognition {
  constructor() { this.phrases = []; this.processLocally = false; }
  start() { this.onerror?.({ error: 'phrases-not-supported' }); this.onend?.(); }
  stop() {}
  abort() {}
}

const ids = [
  'capability', 'diagnoseButton', 'capabilityStatus', 'capabilityReport', 'phase', 'category',
  'expectedTerms', 'servedPipeline', 'recognitionPath', 'contextInput', 'testNativeBiasing',
  'protocolHint', 'recordButton', 'recordStatus', 'rawTranscript', 'memoryTranscript',
  'contextTranscript', 'finalTranscript', 'acceptButton', 'discardButton', 'hypotheses',
  'newVocabulary', 'addVocabulary', 'clearMemory', 'confirmedTerms', 'memoryTable',
  'metricsBody', 'learningBody', 'samplesBody', 'decision', 'jsonExport', 'csvExport',
  'selfTest', 'clearSamples', 'testResult',
];
const nodes = Object.fromEntries(ids.map((id) => [id, new Element()]));
nodes.phase.value = 'teaching';
nodes.category.value = 'known_vocabulary';
nodes.servedPipeline.value = 'raw';
nodes.recognitionPath.value = 'remote';
const local = new Map();
const source = readFileSync(new URL('./index.html', import.meta.url), 'utf8').match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
const window = { SpeechRecognition: PhraseRejectingRecognition, SpeechRecognitionPhrase: class { constructor(text, boost) { this.text = text; this.boost = boost; } } };
const document = { getElementById: (id) => nodes[id], createElement: () => new Element() };
const localStorage = { getItem: (key) => local.get(key) || null, setItem: (key, value) => local.set(key, value) };
const run = new Function('window', 'document', 'localStorage', 'confirm', 'URL', 'Blob', 'navigator', source);
run(window, document, localStorage, () => true, { createObjectURL: () => '', revokeObjectURL: () => {} }, class {}, { userAgent: 'test-chrome' });

const experiment = window.WebSpeechExperiment;
const streamlitAlias = experiment.changedSpan(
  '我想先用streamlet做介面，再看看要不要正式开发。',
  '我想先用 Streamlit 做介面，再看看要不要正式開發。',
  ['Streamlit'],
);
assert.deepEqual(streamlitAlias, {
  rawPhrase: 'streamlet', correctedPhrase: 'Streamlit', kind: 'vocabulary_alias',
  contextBefore: '我想先用', contextAfter: '做介面，再看看要不要正式开发。',
});
assert.equal(experiment.changedSpan('我想先用streamlet做介面。', '我想先用 Streamlit 做介面。', []), null);
experiment.state.correctionMemory = [
  { id: 'legacy', rawPhrase: 'streamlet做介面', correctedPhrase: 'Streamlit 做介面', successfulConfirmations: 9, failedApplications: 0, disabled: false },
  { id: 'streamlit', rawPhrase: 'streamlet', correctedPhrase: 'Streamlit', kind: 'vocabulary_alias', successfulConfirmations: 2, failedApplications: 0, disabled: false },
];
assert.deepEqual(experiment.applyCorrectionMemory('我想先用streamlet做介面。'), { text: '我想先用Streamlit做介面。', applied: ['streamlit'] });
assert.equal(
  experiment.classify({ remotePhrase: 'unsupported', localPhrase: 'untested', availableResult: 'unavailable' }),
  'UNSUPPORTED IN CURRENT ENVIRONMENT',
);

experiment.state.vocabulary = ['ClipAI'];
nodes.testNativeBiasing.checked = true;
nodes.recordButton.click();

assert.match(nodes.recordStatus.textContent, /phrases-not-supported/);
assert.match(nodes.recordStatus.textContent, /未改以無偏誤模式重試/);
assert.equal(experiment.state.nativeCapability.remotePhrase, 'unsupported');
assert.equal(experiment.state.current, null);
console.log('Pass: correction memory requires confirmed evidence, and phrases-not-supported is reported in Traditional Chinese without a silent fallback.');
