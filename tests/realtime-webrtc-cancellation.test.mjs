import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

// Execute the shipped script, with only Swift's string substitutions replaced.
const swift = readFileSync(new URL('../apps/macos/Sources/NaluVoiceStudio/RealtimeVoice.swift', import.meta.url), 'utf8');
const script = swift.split('<script>')[1].split('</script>')[0]
  .replace(/\\#\([^)]*\)/g, 'synthetic-tool');

function harness(stage) {
  let release, entered;
  const gate = new Promise(resolve => { release = resolve; });
  const waiting = new Promise(resolve => { entered = resolve; });
  let paused = false;
  const pause = async where => {
    if (where !== stage || paused) return;
    paused = true;
    entered();
    await gate;
  };
  const records = { requests: [], peers: [], tracks: [], posts: [] };
  class Peer {
    constructor() { records.peers.push(this); this.closed = false; this.answers = 0; }
    addTrack() {}
    createDataChannel() { return { addEventListener() {}, close() {}, send() {} }; }
    async createOffer() { await pause('offer'); return { sdp: 'synthetic' }; }
    async setLocalDescription() { await pause('local'); }
    async setRemoteDescription() { this.answers++; }
    close() { this.closed = true; }
  }
  const context = {
    window: { webkit: { messageHandlers: { naluRealtime: { postMessage: value => records.posts.push(value) } } } },
    document: { createElement: () => ({ remove() {} }), body: { appendChild() {} } },
    navigator: { mediaDevices: { getUserMedia: async () => {
      const track = { stops: 0, stop() { this.stops++; } };
      records.tracks.push(track);
      await pause('microphone');
      return { getTracks: () => [track] };
    } } },
    RTCPeerConnection: Peer, AbortController, setTimeout, clearTimeout,
    fetch: async (url, options) => {
      records.requests.push({ url, options });
      await pause('fetch'); // Ignore abort deliberately: test a late transport result.
      return { ok: true, text: async () => { await pause('body'); return 'synthetic-answer'; } };
    },
  };
  vm.runInNewContext(script, context);
  return { api: context.window.naluRealtime, records, waiting, release: () => release() };
}

for (const stage of ['microphone', 'offer', 'local', 'fetch', 'body']) {
  test(`Stop during ${stage} cannot continue an old handshake`, async () => {
    const h = harness(stage);
    const starting = h.api.start('synthetic-token', 'https://synthetic.invalid/v1/realtime/calls');
    await h.waiting;
    h.api.stop();
    h.release();
    await starting;
    assert.equal(h.records.requests.length, ['fetch', 'body'].includes(stage) ? 1 : 0);
    assert.equal(h.records.peers[0].answers, 0);
    assert.equal(h.records.peers[0].closed, true);
    assert.equal(h.records.tracks[0].stops, 1);
    assert.equal(h.records.posts.filter(p => p.kind === 'error').length, 0);
    if (h.records.requests.length) assert.equal(h.records.requests[0].options.signal.aborted, true);
  });
}

test('Late microphone from an old start cannot close the replacement connection', async () => {
  const h = harness('microphone');
  const old = h.api.start('old', 'https://synthetic.invalid/v1/realtime/calls');
  await h.waiting;
  await h.api.start('new', 'https://synthetic.invalid/v1/realtime/calls');
  h.release();
  await old;
  assert.equal(h.records.requests.length, 1);
  assert.equal(h.records.peers[1].closed, false);
  assert.equal(h.records.peers[1].answers, 1);
  assert.equal(h.records.tracks[0].stops, 1);
  assert.equal(h.records.tracks[1].stops, 0);
  assert.equal(h.records.posts.filter(p => p.kind === 'error').length, 0);
  h.api.stop();
});
