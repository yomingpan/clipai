import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

class Element {
  constructor(value = '') { this.value = value; this.textContent = ''; this.innerHTML = ''; this.className = ''; this.disabled = false; this.listeners = {}; }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  replaceChildren(...children) { this.children = children; if (children[0]?.value) this.value = children[0].value; }
  querySelector() { return new Element(); }
  append() {}
}

class PhraseRejectingRecognition {
  constructor() { this.phrases = []; }
  start() { this.onerror?.({ error: 'phrases-not-supported' }); this.onend?.(); }
  stop() {}
  abort() {}
}

const ids = ['phase', 'category', 'expectedTerms', 'recordButton', 'recordStatus', 'rawTranscript', 'finalTranscript', 'acceptButton', 'discardButton', 'hypotheses', 'capability', 'protocolHint', 'suggestions', 'confirmedTerms', 'metricsTable', 'samplesTable', 'decision', 'testResult', 'confirmTerms', 'clearTerms', 'jsonExport', 'csvExport', 'selfTest', 'clearSamples'];
const nodes = Object.fromEntries(ids.map((id) => [id, new Element()]));
nodes.phase.value = 'adaptation';
const local = new Map();
const source = readFileSync(new URL('./index.html', import.meta.url), 'utf8').match(/<script>\s*([\s\S]*?)\s*<\/script>/)[1];
const window = { SpeechRecognition: PhraseRejectingRecognition, SpeechRecognitionPhrase: class { constructor(text, boost) { this.text = text; this.boost = boost; } } };
const document = { getElementById: (id) => nodes[id], createElement: () => new Element(), querySelectorAll: () => [] };
const localStorage = { getItem: (key) => local.get(key) || null, setItem: (key, value) => local.set(key, value) };
const run = new Function('window', 'document', 'localStorage', 'Option', 'confirm', 'URL', 'Blob', source);
function Option(label, value) { this.label = label; this.value = value; }
run(window, document, localStorage, Option, () => true, { createObjectURL: () => '', revokeObjectURL: () => {} }, class {});

window.WebSpeechExperiment.state.vocabulary = ['ClipAI'];
nodes.phase.value = 'holdout';
nodes.phase.listeners.change();
nodes.recordButton.listeners.click();

assert.match(nodes.recordStatus.textContent, /情境偏誤不受此瀏覽器支援/);
assert.match(nodes.capability.textContent + nodes.capability.innerHTML, /情境偏誤.*不支援/);
assert.equal(nodes.recordButton.disabled, true);
console.log('Pass: runtime phrases-not-supported is reported in Traditional Chinese and blocks the biased holdout.');
