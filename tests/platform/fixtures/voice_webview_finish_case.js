const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("ClipAI/platform/voice_webview_host.html", "utf8");
const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];

async function run(terminal) {
  const events = [];
  const window = {
    pywebview: {api: {emit: event => events.push(event), hide: () => {}}},
    addEventListener: (_name, callback) => callback(),
  };
  class Recognition {
    start() {
      this.onstart();
      const interim = [{transcript: "unfinished phrase"}];
      interim.isFinal = false;
      this.onresult({resultIndex: 0, results: [interim]});
    }
    stop() { this.onend(); }
    abort() { this.onend(); }
  }
  window.SpeechRecognition = Recognition;
  const navigator = {mediaDevices: {getUserMedia: async () => ({getTracks: () => []})}};
  vm.runInNewContext(script, {window, navigator, Uint8Array, Math, setInterval, clearInterval});
  window.clipaiVoice.command({command: "start", capture_id: "capture-1", language: "en-US"});
  await new Promise(resolve => setTimeout(resolve, 0));
  window.clipaiVoice.command({command: terminal, capture_id: "capture-1"});
  return events.filter(event => event.kind === "final" || event.kind === "ended");
}

Promise.all([run("stop"), run("cancel")]).then(results => {
  process.stdout.write(JSON.stringify(results));
});
