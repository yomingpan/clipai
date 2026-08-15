# Web Speech personalization feasibility experiment

This is deliberately throwaway, standalone browser code. It does not integrate
with ClipAI or make any network request. Its job is to gather a small amount of
honest evidence about Chrome Web Speech recognition for a single user's
Chinese-English voice-input workflow.

## Run it in desktop Chrome

1. Open `index.html` in **desktop Chrome**. If Chrome blocks microphone access
   from a `file:` URL, serve this folder with a local static server, for example
   `python -m http.server 8000 -d experiments/web-speech-personalization`, then
   browse to `http://localhost:8000`.
2. Allow microphone permission. The banner must say that Web Speech recognition
   is available. It separately reports whether `SpeechRecognitionPhrase` is
   supported; do not treat an unsupported holdout run as a biased run.
3. In Stage 1, select each of the three categories and collect four natural
   utterances per category (12 total). Leave the reference field empty until a
   final recognition result appears, then correct it to the actual spoken text
   and accept it. Add any expected technical terms before recording.
4. Review the vocabulary suggestions. They are only suggestions from adaptation
   corrections. Select and confirm the terms you actually want in your personal
   vocabulary. Confirmed terms persist in browser local storage.
5. Switch to Stage 2. Collect 8 new sentences containing confirmed vocabulary,
   4 with unseen English terms, and 4 Mandarin-only controls. This phase applies
   the confirmed phrases at boost 3 only when the browser supports the API.
6. Use the individual-sample table to inspect every hypothesis and the dashboard
   to inspect aggregates. Export JSON and CSV before clearing browser data.

The dashboard's baseline versus holdout comparison is **not paired**: an
utterance is recognized under one condition. It is an N-of-1 feasibility signal,
not a causal or population claim. If it is ambiguous, collect more holdout data
rather than changing application architecture.

## What is stored

The experiment saves accepted samples and explicitly confirmed vocabulary under
two namespaced `localStorage` keys. Recognition hypotheses, timestamps, manual
correction, and calculated metrics are retained only in that Chrome profile.
`Clear all samples` and `Clear confirmed vocabulary` remove those respective
local records.

## Metrics

- Mixed error rate tokenizes Han characters individually and runs contiguous
  English/number tokens as words. Punctuation and whitespace are ignored.
- Technical-term recall is expected canonical terms found in the transcript.
  Case is ignored, but split terms such as `Fast API` do not count as `FastAPI`.
  Precision is intentionally not claimed because the experiment does not have
  an annotated universe of non-expected terms.
- Human correction cost measures time from the first edit (or accept, if no
  edit) through accept, edit distance, and accept-without-edit.
- The first `postProcess` implementation is identity-only. It exposes the
  required isolated interface and cannot introduce a harmful correction; future
  deterministic or LLM strategies can be compared using the recorded samples.
- Latency reports both speech-end to final-result and final-result to accept
  median/p95 values when the browser supplied a speech-end event.

Use **Run metric self-check** before a session to verify the tokenizer and
alignment implementation with a punctuation-insensitive Chinese-English case.
