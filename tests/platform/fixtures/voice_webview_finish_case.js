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

async function runNetworkFailure() {
  const events = [];
  const window = {
    pywebview: {api: {emit: event => events.push(event), hide: () => {}}},
    addEventListener: (_name, callback) => callback(),
  };
  class Recognition {
    start() {
      this.onstart();
      this.onerror({error: "network"});
    }
  }
  window.SpeechRecognition = Recognition;
  const navigator = {mediaDevices: {getUserMedia: async () => ({getTracks: () => []})}};
  vm.runInNewContext(script, {window, navigator, Uint8Array, Math, setInterval, clearInterval});
  window.clipaiVoice.command({command: "start", capture_id: "capture-network", language: "zh-TW"});
  await new Promise(resolve => setTimeout(resolve, 0));
  return events.filter(event => event.kind === "failed" || event.kind === "ended");
}

async function runNetworkAfter(terminal) {
  const events = [];
  const window = {
    pywebview: {api: {emit: event => events.push(event), hide: () => {}}},
    addEventListener: (_name, callback) => callback(),
  };
  class Recognition {
    start() { this.onstart(); }
    stop() { this.onerror({error: "network"}); this.onend(); }
    abort() { this.onerror({error: "network"}); this.onend(); }
  }
  window.SpeechRecognition = Recognition;
  const navigator = {mediaDevices: {getUserMedia: async () => ({getTracks: () => []})}};
  vm.runInNewContext(script, {window, navigator, Uint8Array, Math, setInterval, clearInterval});
  window.clipaiVoice.command({command: "start", capture_id: "capture-late-network", language: "zh-TW"});
  await new Promise(resolve => setTimeout(resolve, 0));
  window.clipaiVoice.command({command: terminal, capture_id: "capture-late-network"});
  return events.filter(event => event.kind === "failed" || event.kind === "ended");
}

Promise.all([run("stop"), run("cancel"), runNetworkFailure(), runNetworkAfter("stop"), runNetworkAfter("cancel")]).then(results => {
  process.stdout.write(JSON.stringify(results));
});
