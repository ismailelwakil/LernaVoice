"""Voice-choice polish for the demo page.

Two things that decide whether the tutor *sounds* human in the hosted preview,
where the browser does the speaking:

  * Arabic should use an Egyptian voice when the device has one (the tutor
    teaches Egyptian Arabic, and a Gulf/MSA voice on Egyptian text sounds off).
  * When the device has **no** voice for the chosen language (Igbo, Yoruba and
    Amharic are common cases), say so in the panel instead of silently speaking
    English text with an English voice.

Adds `voiceAvailability()` to the harness exports and exposes the notice as
`#ttsnote`.
"""

P = "app/static/voice_mode.html"
s = open(P).read()

# 1) locale nuance: prefer the regional voice the tutor is actually teaching.
old = """  const score = (v)=>{
    const n = (v.name || '').toLowerCase();
    let sc = 0;
    if(/natural|neural|premium|enhanced|siri/.test(n)) sc += 8;   // best quality first
    if(/google/.test(n)) sc += 5;
    if(/samantha|ava|allison|serena|daniel|karen|moira|tessa|zira|aria|jenny|guy|joanna|matthew/.test(n)) sc += 3;
    if(v.localService) sc += 1;
    if(/compact|espeak|festival|pico|robot/.test(n)) sc -= 5;     // last resort
    return sc;
  };"""
new = """  const score = (v)=>{
    const n = (v.name || '').toLowerCase();
    const l = (v.lang || '').toLowerCase();
    let sc = 0;
    if(/natural|neural|premium|enhanced|siri/.test(n)) sc += 8;   // best quality first
    if(/google/.test(n)) sc += 5;
    if(/samantha|ava|allison|serena|daniel|karen|moira|tessa|zira|aria|jenny|guy|joanna|matthew/.test(n)) sc += 3;
    if(want === 'ar' && /(^|-)eg($|-)|egypt|amira|salma|hoda|shakir/.test(l + ' ' + n)) sc += 6; // we teach Egyptian
    if(v.localService) sc += 1;
    if(/compact|espeak|festival|pico|robot/.test(n)) sc -= 5;     // last resort
    return sc;
  };"""
assert old in s
s = s.replace(old, new, 1)

# 2) language coverage, reported instead of hidden.
old = """function applyVoiceForLanguage(){
  const want = (CFG.language || 'en').toLowerCase();
  const keep = ttsVoice && (ttsVoice.lang || '').toLowerCase().startsWith(want);
  if(!keep) ttsVoice = pickVoice(CFG.language);
  const exact = ttsVoices.some(v => (v.lang || '').toLowerCase().startsWith(want));
  $('d-tts').textContent = !TTS_OK ? 'not available in this browser'
      : (ttsVoice ? ttsVoice.name + ' · ' + ttsVoice.lang + (exact ? '' : ' (no ' + CFG.language + ' voice installed → falling back)')
                  : 'system default');
  $('d-nvoices').textContent = TTS_OK ? ttsVoices.length + ' installed' : '—';
}"""
new = """/* Is there a voice on *this device* for this language? If not, the demo must
   say so: an English voice reading Yoruba is the most robotic outcome of all. */
function voiceAvailability(){
  const want = (CFG.language || 'en').toLowerCase();
  if(!TTS_OK) return { available:false, reason:'no speech synthesis in this browser' };
  const match = ttsVoices.filter(v => (v.lang || '').toLowerCase().startsWith(want));
  if(match.length) return { available:true, count:match.length };
  return { available:false, reason:'no ' + (CFG.language || 'en').toUpperCase() + ' voice installed' };
}

function applyVoiceForLanguage(){
  const want = (CFG.language || 'en').toLowerCase();
  const keep = ttsVoice && (ttsVoice.lang || '').toLowerCase().startsWith(want);
  if(!keep) ttsVoice = pickVoice(CFG.language);
  const avail = voiceAvailability();
  $('d-tts').textContent = !TTS_OK ? 'not available in this browser'
      : (ttsVoice ? ttsVoice.name + ' · ' + ttsVoice.lang + (avail.available ? '' : ' (not a ' + CFG.language + ' voice)')
                  : 'system default');
  $('d-nvoices').textContent = TTS_OK ? ttsVoices.length + ' installed' : '—';
  const note = $('ttsnote');
  if(note){
    note.style.display = avail.available ? 'none' : '';
    note.textContent = avail.available ? ''
      : 'This device has ' + (avail.reason || 'no matching voice') + '. Install one (Windows: Settings → '
        + 'Time & language → Speech; Android/iOS: system text-to-speech), or switch Voice mode to '
        + '“service” to hear the voice the service generates.';
  }
}"""
assert old in s
s = s.replace(old, new, 1)

# 3) the notice element, right under the voice picker
old = """      <select id="voicesel" style="flex:1;background:#141924;border:1px solid #222b3c;color:#dbe4f2;border-radius:6px;padding:4px;font-size:11.5px"></select></div>"""
new = old + """
    <div id="ttsnote" style="display:none;margin-top:6px;font-size:11px;line-height:1.45;color:#f0c674"></div>"""
assert old in s
s = s.replace(old, new, 1)

# 4) harness export
if "voiceAvailability," not in s and "EXPORTS" in s:
    import re
    m = re.search(r"(\bconst EXPORTS\b[^\n]*?)'", s)
    s = s.replace("speakable,", "speakable,voiceAvailability,", 1) if "speakable," in s else s

open(P, "w").write(s)
print("voice choice polished;", "voiceAvailability" in s, "ttsnote" in s)
