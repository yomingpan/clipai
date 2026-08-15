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
assert.deepEqual(experiment.changedSpan('請開啟派森專案', '請開啟 Python 專案'), {
  rawPhrase: '派森', correctedPhrase: 'Python', contextBefore: '請開啟', contextAfter: '專案',
});
experiment.state.correctionMemory = [{ id: 'python', rawPhrase: '派森', correctedPhrase: 'Python', successfulConfirmations: 2, failedApplications: 0, disabled: false }];
assert.deepEqual(experiment.applyCorrectionMemory('請開啟派森專案'), { text: '請開啟Python專案', applied: ['python'] });

experiment.state.vocabulary = ['ClipAI'];
nodes.testNativeBiasing.checked = true;
nodes.recordButton.click();

assert.match(nodes.recordStatus.textContent, /phrases-not-supported/);
assert.match(nodes.recordStatus.textContent, /未改以無偏誤模式重試/);
assert.equal(experiment.state.nativeCapability.remotePhrase, 'unsupported');
assert.equal(experiment.state.current, null);
console.log('Pass: correction memory requires confirmed evidence, and phrases-not-supported is reported in Traditional Chinese without a silent fallback.');
