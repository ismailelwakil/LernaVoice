"""Client-side audio verification.

The voice screen is what turns `assistant.audio.chunk` events into sound, and
that logic runs in the browser, so pytest cannot reach it directly. These tests
extract the real client JavaScript out of `app/static/voice_mode.html` (the page
the service serves at `/`), run it in Node against a stubbed Web Audio API, and
assert on the playback schedule it produces — i.e. they check that audio is
actually played, continuously, and that barge-in stops it.

Skipped automatically when Node is not installed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "app" / "static" / "voice_mode.html"
CONSOLE = ROOT / "app" / "static" / "console.html"

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

#: Minimal browser environment + a fake Web Audio API that records every
#: scheduled buffer source, so the tests can assert on real timing.
HARNESS = r"""
function el(){ return { textContent:'', innerHTML:'', value:'', disabled:false, title:'',
  className:'', classList:{add(){},remove(){},toggle(){}}, style:{}, scrollTop:0,
  appendChild(){}, addEventListener(){}, set onclick(f){this._c=f}, get onclick(){return this._c} }; }
const els = {};
const cfgText = require('fs').readFileSync(process.argv[3], 'utf8');
const cfgObj = JSON.parse(cfgText);
global.document = {
  getElementById:(i)=> i === 'cfg' ? { textContent: cfgText } : (els[i] = els[i] || el()),
  createElement:()=>el(), body:{className:''}, addEventListener(){} };
global.window = {};
global.location = process.env.EMBEDDED_IFRAME
  ? { hostname:'3000-abc.e2b.app', host:'3000-abc.e2b.app', protocol:'https:', origin:'null',
      href:'https://3000-abc.e2b.app/voice', pathname:'/voice', search:'' }
  : { hostname:'8501-abcdef.e2b.app', host:'8501-abcdef.e2b.app', protocol:'https:',
      origin:'https://8501-abcdef.e2b.app', href:'https://8501-abcdef.e2b.app/', pathname:'/', search:'' };
if(process.env.EMBEDDED_IFRAME){ global.window.self = { name:'frame' }; global.window.top = { name:'top' }; }
else { global.window.self = { name:'top' }; global.window.top = global.window.self; }
global.window.self.name = global.window.self.name;
const sockets = [];
global.WebSocket = class {
  constructor(url){ this.url = url; sockets.push(url); this.readyState = 1; }
  send(){} close(){}
};
global.fetch = async (url)=>{
  const path = String(url);
  const body = path.includes('/voice/session/') && path.endsWith('/token')
    ? '{"token":"vst_test"}'
    : path.endsWith('/voice/session') ? '{"session_id":"vs_test_1"}'
    : '{"service":"lerna-voice-ai","status":"ok"}';
  return { ok:true, status:200, text:async()=>body };
};
global.navigator = { mediaDevices:{ getUserMedia: async()=>({ getTracks:()=>[{stop(){}}] }) } };
global.atob = (s)=>Buffer.from(s,'base64').toString('binary');

let clock = 0;
const starts = [], stopped = [];
class FakeBuffer{ constructor(len, rate){ this.length=len; this.sampleRate=rate;
  this.duration=len/rate; this._d=new Float32Array(len); } getChannelData(){ return this._d; } }
class FakeSource{ constructor(ctx){ this.ctx=ctx; } connect(){} start(t){ this.t=t; starts.push(t); }
  stop(){ this.stopped=true; stopped.push(this); } }
class Ctx{
  constructor(o){ this.sampleRate=(o&&o.sampleRate)||48000; this.state='running'; }
  get currentTime(){ return clock; }
  createGain(){ return { gain:{value:1}, connect(){} }; }
  createBuffer(c,l,r){ return new FakeBuffer(l,r); }
  createBufferSource(){ return new FakeSource(this); }
  createMediaStreamSource(){ return { connect(){}, disconnect(){} }; }
  createScriptProcessor(){ return { connect(){}, disconnect(){}, onaudioprocess:null }; }
  resume(){ this.state='running'; return Promise.resolve(); }
  close(){ return Promise.resolve(); }
  get destination(){ return {}; }
}
global.window.AudioContext = Ctx;

/* stub the Web Speech API and record what the page asks it to say */
const spoken = [], cancelled = [];
global.SpeechSynthesisUtterance = class { constructor(t){ this.text = t; } };
global.window.speechSynthesis = {
  speaking:false,
  speak(u){ spoken.push(u.text); this.speaking = true; if(u.onstart) u.onstart();
            this.speaking = false; if(u.onend) u.onend(); },
  cancel(){ cancelled.push(1); this.speaking = false; },
  getVoices(){ return [
    { name:'English (United States) Compact', lang:'en-US', localService:true, voiceURI:'compact' },
    { name:'Samantha Enhanced', lang:'en-US', localService:true, voiceURI:'samantha' },
    { name:'Google US English Natural', lang:'en-US', localService:false, voiceURI:'google-natural' },
    { name:'Amira', lang:'ar-EG', localService:true, voiceURI:'amira' },
    { name:'Maged', lang:'ar-SA', localService:true, voiceURI:'maged' },
  ]; },
  addEventListener(){},
};

function chunk(ms, freq){
  const n = Math.round(24000*ms/1000), i16 = new Int16Array(n);
  for(let i=0;i<n;i++) i16[i] = Math.round(Math.sin(2*Math.PI*freq*i/24000)*12000);
  return i16;
}
const client = require(require('path').resolve(process.argv[2]));
const { playPcm, stopPlayback, serviceBase, handle, ensureAudio } = client;
/* The page defaults to the browser voice; the checks below opt into both
   engines so the PCM path is exercised too, then test the modes explicitly. */
client.setVoiceMode('both');

const out = { checks:{}, values:{} };
function check(name, cond, value){ out.checks[name] = !!cond; out.values[name] = value; }

/* 1 — where the page looks for the service */
check('serviceBase_rewrites_sandbox_host',
      serviceBase() === 'https://3000-abcdef.e2b.app', serviceBase());
check('serviceBase_is_relative_when_same_origin',
      cfgObj.serviceUrl ? true : serviceBase() === '', serviceBase());

/* 2 — chunks are scheduled back-to-back: continuous audio, no gaps, no overlap */
ensureAudio();
starts.length = 0;
playPcm(chunk(100, 440)); clock += 0.02;
playPcm(chunk(100, 660)); clock += 0.02;
playPcm(chunk(100, 880));
const gap1 = starts[1]-starts[0], gap2 = starts[2]-starts[1];
out.values.starts = starts.map(v=>+v.toFixed(4));
check('schedules_every_chunk', starts.length === 3, starts.length);
check('chunks_play_back_to_back',
      Math.abs(gap1-0.1) < 0.005 && Math.abs(gap2-0.1) < 0.005, [+gap1.toFixed(4), +gap2.toFixed(4)]);
check('playback_starts_immediately', starts[0] > 0.03 && starts[0] < 0.06, +starts[0].toFixed(4));

/* 3 — amplitude survives decoding: a silent stream would still "play" */
let captured = null;
class Cap extends Ctx{ constructor(){ super({sampleRate:24000}); }
  createBuffer(c,l,r){ captured = new FakeBuffer(l,r); return captured; } }
client.setCtx(new Cap());
playPcm(chunk(100, 440));
const data = captured.getChannelData(0);
let peak = 0, zc = 0;
for(let i=0;i<data.length;i++){ peak = Math.max(peak, Math.abs(data[i]));
  if(i && (data[i-1]<0)!==(data[i]<0)) zc++; }
check('decoded_audio_is_audible', peak > 0.3, +peak.toFixed(3));
check('output_is_a_waveform_not_dc',
      zc > 30, zc);
check('chunk_length_preserved', Math.abs(captured.duration-0.1) < 1e-6, captured.duration);

/* 4 — a 48 kHz output device still gets the full 100 ms at the right pitch */
class Ctx48 extends Ctx{ constructor(){ super({sampleRate:48000}); }
  createBuffer(c,l,r){ captured = new FakeBuffer(l,r); return captured; } }
client.setCtx(new Ctx48());
playPcm(chunk(100, 440));
let zc48 = 0; const d48 = captured.getChannelData(0);
for(let i=1;i<d48.length;i++) if((d48[i-1]<0)!==(d48[i]<0)) zc48++;
const pitch = zc48/2/captured.duration;
check('resamples_for_48khz_device',
      Math.abs(captured.duration-0.1) < 0.002 && Math.abs(pitch-440) < 10,
      [+captured.duration.toFixed(4), +pitch.toFixed(1)]);

/* 5 — an incoming event is decoded and queued without waiting for the turn end */
client.setCtx(new Ctx());
const before = starts.length;
playPcm(chunk(10, 300));                    // reset the scheduler with a tiny chunk
const queuedBefore = starts.length;
const b64 = Buffer.from(chunk(80, 300).buffer).toString('base64');
handle({ event:'assistant.audio.chunk', audio:b64, sample_rate:24000 });
check('audio_event_decoded_and_played', starts.length === queuedBefore + 1,
      [starts.length - queuedBefore, before]);

/* 6 — barge-in stops playback instantly (§23) */
playPcm(chunk(400, 220));
const queued = starts.length;
stopPlayback();
check('interrupt_stops_playback', queued > 0 && stopped.length > 0, stopped.length);

/* 7 — every §33 event type is handled without throwing */
let error = null;
try{
  ['assistant.response.started','assistant.text.delta','assistant.response.completed',
   'input.transcript','assistant.interrupted','checkpoint.created','resume.completed',
   'session.recap','visual.updated','language.changed','provider.switched','session.ended',
   'error','latency','session.state_changed'].forEach(ev=>handle({ event:ev, text:'x',
   final:true, message:'m', checkpoint:{}, concepts_covered:[], latency:1,
   visual:{type:'code',content:'c'}, to:'ig', from:'a'}));
}catch(e){ error = e.message; }
check('handles_all_event_types', error === null, error);

/* 8 — the assistant transcript is voiced, sentence by sentence */
cancelled.length = 0; spoken.length = 0;
handle({ event:'assistant.response.started' });
handle({ event:'assistant.text.delta', text:'Hello there. Welcome to binary search.' });
const afterDelta = spoken.length;
handle({ event:'assistant.response.completed', text:'Hello there. Welcome to binary search.' });
check('speaks_each_sentence_once', spoken.length === 2 && afterDelta === 1,
      { spoken: spoken.slice(), afterDelta });
check('no_duplicate_speech_on_turn_end', spoken.length === 2, spoken.slice());
check('picks_the_best_installed_voice',
      client.chosenVoiceName && client.chosenVoiceName === 'Google US English Natural',
      client.chosenVoiceName);

/* 9 — barge-in silences the voice immediately */
cancelled.length = 0; spoken.length = 0;
handle({ event:'assistant.text.delta', text:'This is a long explanation that keeps going and going' });
handle({ event:'assistant.interrupted' });
check('interrupt_cancels_speech', cancelled.length >= 1, cancelled.length);

/* 10 — service mode plays PCM and stays silent */
client.setVoiceMode('service');
const beforeStarts = starts.length;
spoken.length = 0;
const b64b = Buffer.from(chunk(60, 300).buffer).toString('base64');
handle({ event:'assistant.text.delta', text:'Service mode says nothing in the browser.' });
handle({ event:'assistant.audio.chunk', audio:b64b, sample_rate:24000 });
check('service_mode_is_silent_in_the_browser', spoken.length === 0, spoken.slice());
check('service_mode_plays_service_pcm', starts.length > beforeStarts, starts.length - beforeStarts);

/* 10b — the voice reads the *spoken* form, not the written one. A synthesiser
   given "mid = (low + high) // 2" says punctuation names; a tutor says words. */
check('speakable_turns_maths_into_words',
      client.speakable('mid = (low + high) // 2') === 'mid equals low plus high divided by 2',
      client.speakable('mid = (low + high) // 2'));
check('speakable_removes_dashes_and_brackets',
      client.speakable('first — then (again)') === 'first, then again',
      client.speakable('first — then (again)'));
spoken.length = 0;
client.setVoiceMode('browser');
handle({ event:'assistant.text.delta', text:'The midpoint is mid = (low + high) // 2.' });
check('the_voice_hears_words_not_symbols',
      spoken.length > 0 && !/[\\/|=(]/.test(spoken.join(' ')), spoken.slice());
client.setVoiceMode('both');

/* 10c — the voice must follow a language switch, and a missing local voice
   must be admitted rather than papered over with the previous language's voice. */
handle({ event:'language.changed', to:'ar' });
check('voice_follows_language_switch', /maged/i.test(client.chosenVoiceName || ''),
      { chosen: client.chosenVoiceName, avail: client.voiceAvailability() });
check('fusHa_is_preferred_over_the_dialect_voice', !/amira/i.test(client.chosenVoiceName || ''),
      client.chosenVoiceName);
check('arabic_uses_an_available_voice', client.voiceAvailability().available === true,
      { avail: client.voiceAvailability(), chosen: client.chosenVoiceName });
handle({ event:'language.changed', to:'ig' });
const ig = client.voiceAvailability();
check('a_missing_voice_is_reported', ig.available === false && /IG/.test(ig.reason || ''), ig);
handle({ event:'language.changed', to:'en' });
check('switch_back_restores_the_english_voice',
      client.voiceAvailability().available === true && /google us english natural/i.test(client.chosenVoiceName || ''),
      client.chosenVoiceName);

/* 11 — browser mode counts the PCM without playing it (diagnostics stay honest) */
client.setVoiceMode('browser');
const beforeStarts2 = starts.length;
handle({ event:'assistant.audio.chunk', audio:b64b, sample_rate:24000 });
check('browser_mode_does_not_double_play_pcm', starts.length === beforeStarts2, starts.length - beforeStarts2);
check('browser_mode_still_counts_pcm_bytes', client.audioCounters().bytes > 0, client.audioCounters().bytes);

/* 12 — the sandboxed preview iframe: opaque origin plus an embedding frame.
   `location.origin` is the string "null" there, which used to produce a broken
   `new WebSocket("null/…")` and made the preview look dead. */
(async ()=>{
  if(process.env.EMBEDDED_IFRAME){
    check('host_origin_comes_from_protocol_and_host',
          client.HOST_ORIGIN === 'https://3000-abc.e2b.app', client.HOST_ORIGIN);
    check('ws_base_ignores_the_opaque_origin',
          client.WS_BASE === 'wss://3000-abc.e2b.app', client.WS_BASE);
    check('opaque_origin_is_detected', client.IS_OPAQUE === true, client.IS_OPAQUE);
    check('embedding_is_detected', client.IS_EMBEDDED === true, client.IS_EMBEDDED);
    try { await client.openSession(); } catch(e){ out.values.openError = e.message; }
    check('socket_url_is_absolute_and_routed',
          sockets.length === 1 && sockets[0].startsWith('wss://3000-abc.e2b.app/voice/session/vs_test_1/audio'),
          sockets[0]);
    check('token_is_attached_to_the_socket_url',
          sockets[0] && sockets[0].includes('token=vst_test'), sockets[0]);
    check('embedded_preview_offers_a_top_level_link',
          client.embeddedHint().includes('its own tab') &&
          client.embeddedHint().includes('https://3000-abc.e2b.app/voice'),
          client.embeddedHint());
  }
  console.log('RESULT ' + JSON.stringify(out));
  process.exit(0);   // the page's setInterval would otherwise keep node alive
})();
"""


def _client_config(service_url: str = "http://localhost:3000") -> dict:
    return {
        "serviceUrl": service_url,
        "servicePort": "3000",
        "apiKey": "",
        "student_id": "demo-student-001",
        "course_id": "algorithms-101",
        "lesson_id": "lesson-binary-search",
        "topic": "Binary Search",
        "language": "en",
        "resume_latest": False,
        "languages": {"en": "English", "ig": "Igbo"},
    }


# One export list, shared by every client.js build below: three copies of it once
# drifted apart, and a missing export shows up as a confusing Node failure.
EXPORTS = (
    "\nmodule.exports={playPcm,stopPlayback,serviceBase,handle,ensureAudio,setVoiceMode,"
    "openSession,get WS_BASE(){return WS_BASE;},get HOST_ORIGIN(){return HOST_ORIGIN;},"
    "get IS_EMBEDDED(){return IS_EMBEDDED;},get IS_OPAQUE(){return IS_OPAQUE;},"
    "embeddedHint,tabUrl,speakable,voiceAvailability,"
    "get chosenVoiceName(){return ttsVoice && ttsVoice.name;},"
    "audioCounters:()=>({bytes:bytesIn,chunks:chunksIn}),"
    "setCtx:(c)=>{actx=c;gain=c.createGain();}};\n"
)

def _client_js(service_url: str = "http://localhost:3000") -> str:
    """The page as the browser receives it: the template + an injected config."""
    config = _client_config(service_url)
    html = re.sub(
        r'(<script id="cfg" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + json.dumps(config) + m.group(2),
        PAGE.read_text(encoding="utf-8"),
        count=1,
        flags=re.S,
    )
    return re.search(r"<script>\n(.*?)</script>", html, re.S).group(1)


def _console_js() -> str:
    return re.search(r"<script>(.*?)</script>", CONSOLE.read_text(), re.S).group(1)


def _run_harness(
    tmp: Path, service_url: str = "http://localhost:3000", embedded: bool = False
) -> dict:
    """Run the real client JS in Node and return the harness results."""
    (tmp / "client.js").write_text(
        _client_js()
        + EXPORTS
    )
    (tmp / "config.json").write_text(json.dumps(_client_config(service_url)))
    (tmp / "harness.js").write_text(HARNESS)
    env = {**os.environ, "EMBEDDED_IFRAME": "1"} if embedded else None
    proc = subprocess.run(
        ["node", str(tmp / "harness.js"), str(tmp / "client.js"), str(tmp / "config.json")],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, f"node failed:\n{proc.stdout}\n{proc.stderr}"
    line = [l for l in proc.stdout.splitlines() if l.startswith("RESULT ")]
    assert line, f"no result from the harness:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(line[-1][len("RESULT ") :])


@pytest.fixture(scope="module")
def client_audio(tmp_path_factory) -> dict:
    """The page as embedded elsewhere (Streamlit on :8501)."""
    tmp = tmp_path_factory.mktemp("client")
    (tmp / "client.js").write_text(
        _client_js()
        + EXPORTS
    )
    return _run_harness(tmp)


@pytest.fixture(scope="module")
def same_origin(tmp_path_factory) -> dict:
    """The page as served by the service itself (relative URLs)."""
    tmp = tmp_path_factory.mktemp("client_same_origin")
    (tmp / "client.js").write_text(
        _client_js(service_url="")
        + EXPORTS
    )
    return _run_harness(tmp, service_url="")


@pytest.fixture(scope="module")
def embedded_preview(tmp_path_factory) -> dict:
    """The page inside a sandboxed preview iframe: opaque origin, framed."""
    tmp = tmp_path_factory.mktemp("client_embedded")
    (tmp / "client.js").write_text(_client_js(service_url="") + EXPORTS)
    return _run_harness(tmp, service_url="", embedded=True)


@requires_node
def test_preview_iframe_still_builds_a_working_socket_url(embedded_preview):
    """`location.origin` is "null" in a sandboxed iframe — the socket URL must not be.

    This was a real dead end: the page concatenated `location.origin` with the WS
    path, so an embedded preview tried `new WebSocket("null/voice/session/…")`,
    threw, and the demo looked broken however healthy the service was.
    """
    checks, values = embedded_preview["checks"], embedded_preview["values"]
    assert checks["host_origin_comes_from_protocol_and_host"], values
    assert checks["ws_base_ignores_the_opaque_origin"], values
    assert checks["opaque_origin_is_detected"] and checks["embedding_is_detected"], values
    assert checks["socket_url_is_absolute_and_routed"], values.get("openError") or values
    assert checks["token_is_attached_to_the_socket_url"], values


@requires_node
def test_embedded_preview_points_at_the_top_level_page(embedded_preview):
    """A framed preview can block the mic, so the page offers its own tab."""
    checks, values = embedded_preview["checks"], embedded_preview["values"]
    assert checks["embedded_preview_offers_a_top_level_link"], values


@requires_node
def test_client_javascript_is_valid(client_audio):
    """The engine above only proves anything if the page still parses."""
    assert client_audio["checks"], "harness produced no checks"


@requires_node
def test_assistant_audio_plays_back_to_back(client_audio):
    """The user-visible requirement: assistant audio is heard, continuously."""
    checks = client_audio["checks"]
    assert checks["schedules_every_chunk"], client_audio["values"]
    assert checks["chunks_play_back_to_back"], client_audio["values"]["chunks_play_back_to_back"]
    assert checks["playback_starts_immediately"], client_audio["values"]["playback_starts_immediately"]


@requires_node
def test_playback_is_audible_and_resampled(client_audio):
    checks = client_audio["checks"]
    assert checks["decoded_audio_is_audible"], client_audio["values"]["decoded_audio_is_audible"]
    assert checks["output_is_a_waveform_not_dc"], client_audio["values"]["output_is_a_waveform_not_dc"]
    assert checks["resamples_for_48khz_device"], client_audio["values"]["resamples_for_48khz_device"]


@requires_node
def test_streamed_chunk_and_barge_in(client_audio):
    checks = client_audio["checks"]
    assert checks["audio_event_decoded_and_played"]
    assert checks["interrupt_stops_playback"], client_audio["values"]["interrupt_stops_playback"]
    assert checks["handles_all_event_types"], client_audio["values"]["handles_all_event_types"]


@requires_node
def test_sandbox_host_derivation(client_audio):
    """Embedded elsewhere (Streamlit on :8501) the page still finds the service."""
    assert client_audio["checks"]["serviceBase_rewrites_sandbox_host"], client_audio["values"]


@requires_node
def test_assistant_is_voiced_sentence_by_sentence(client_audio):
    """The clear-voice requirement: each sentence is spoken once, as it arrives."""
    checks = client_audio["checks"]
    assert checks["speaks_each_sentence_once"], client_audio["values"]["speaks_each_sentence_once"]
    assert checks["no_duplicate_speech_on_turn_end"]
    assert checks["picks_the_best_installed_voice"], client_audio["values"]["picks_the_best_installed_voice"]


@requires_node
def test_the_voice_follows_the_language(client_audio):
    """Switch to Arabic and the tutor reads Arabic; no voice for Igbo is admitted."""
    checks, values = client_audio["checks"], client_audio["values"]
    assert checks["voice_follows_language_switch"], values
    assert checks["fusHa_is_preferred_over_the_dialect_voice"], values
    assert checks["arabic_uses_an_available_voice"], values
    assert checks["a_missing_voice_is_reported"], values
    assert checks["switch_back_restores_the_english_voice"], values


@requires_node
def test_the_voice_speaks_words_not_symbols(client_audio):
    """What the synthesiser receives must be speech, not a written equation."""
    checks, values = client_audio["checks"], client_audio["values"]
    assert checks["speakable_turns_maths_into_words"], values
    assert checks["speakable_removes_dashes_and_brackets"], values
    assert checks["the_voice_hears_words_not_symbols"], values


@requires_node
def test_interrupt_silences_the_voice(client_audio):
    assert client_audio["checks"]["interrupt_cancels_speech"], client_audio["values"]["interrupt_cancels_speech"]


@requires_node
def test_voice_engines_are_selectable(client_audio):
    """Browser voice, the service's PCM, or both — and the diagnostics stay honest
    either way (bytes are counted even when the PCM is not played)."""
    checks = client_audio["checks"]
    assert checks["service_mode_is_silent_in_the_browser"], client_audio["values"]["service_mode_is_silent_in_the_browser"]
    assert checks["service_mode_plays_service_pcm"]
    assert checks["browser_mode_does_not_double_play_pcm"]
    assert checks["browser_mode_still_counts_pcm_bytes"], client_audio["values"]["browser_mode_still_counts_pcm_bytes"]


@requires_node
def test_same_origin_mode_uses_relative_urls(same_origin):
    """Served by the service itself, the page must talk to its own origin.

    Cross-port calls are the first thing a port proxy blocks, so the default
    (empty `serviceUrl`) has to produce relative URLs on the same host as the
    WebSocket — this is the configuration the preview runs in."""
    checks = same_origin["checks"]
    assert checks["serviceBase_is_relative_when_same_origin"], same_origin["values"]
    # and everything else still works in that mode
    assert checks["chunks_play_back_to_back"]
    assert checks["audio_event_decoded_and_played"]


@requires_node
def test_service_console_js_is_valid_and_streams_audio(tmp_path):
    """The service's own console must stream too, not buffer until a button."""
    src = _console_js()
    path = tmp_path / "console.js"
    path.write_text(src)
    proc = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "queueChunk(u);" in src, "assistant.audio.chunk must queue playback directly"
    assert "live = [], nextAt = 0;" in src, "streaming playback queue missing"
