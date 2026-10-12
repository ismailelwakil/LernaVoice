"""Round 16, part 5: the voice screen offers Arabic twice (Egyptian + fusHa).

Run once from the service root:  python3 tools/patch_arabic_ui.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs, all_=False):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new) if all_ else s.replace(old, new, 1)
    write(path, s)


sub("app/static/voice_mode.html", [
    # 1. the picker: Arabic twice, and a line explaining the difference
    (
        '''  "languages": {"en":"English","ar":"العربية · Arabic","fr":"Français","sw":"Kiswahili",
    "am":"አማርኛ · Amharic","ha":"Hausa","so":"Soomaali","yo":"Yorùbá","ig":"Igbo","zu":"isiZulu"}''',
        '''  "languages": {"en":"English","ar-EG":"العربية المصرية · Arabic (Egyptian)",
    "ar-MSA":"العربية الفصحى · Arabic (fusHa)","fr":"Français","sw":"Kiswahili",
    "am":"አማርኛ · Amharic","ha":"Hausa","so":"Soomaali","yo":"Yorùbá","ig":"Igbo","zu":"isiZulu"}''',
    ),
    (
        '''    <div class="hint">Language switches the live lesson straight away — the tutor acknowledges''',
        '''    <div class="hint"><b>Arabic has two registers:</b> <b>العربية المصرية</b> speaks with the
      Egyptian voice (<code>ar-EG-SalmaNeural</code>) and the Egyptian phrase set;
      <b>العربية الفصحى</b> speaks with the MSA voice (<code>ar-SA-ZariyahNeural</code>) and formal
      lines. Same lesson, same plan, same checkpoint — only the register changes, and you can
      switch between them mid-lesson.<br />
      Language switches the live lesson straight away — the tutor acknowledges''',
    ),
    # 2. UI code -> (language, dialect) on the wire
    (
        '''const CFG = JSON.parse(document.getElementById('cfg').textContent);''',
        '''const CFG = JSON.parse(document.getElementById('cfg').textContent);
/* A UI language code may carry a dialect (`ar-EG` / `ar-MSA`). The service wants
   `language` + `dialect`; the browser voice picker only wants the base language. */
function langBase(code){ return String(code || 'en').split('-')[0].toLowerCase(); }
function langDialect(code){ const p = String(code || '').split('-'); return p.length > 1 ? p.join('-') : null; }''',
    ),
    (
        '''    student_id:CFG.student_id, language:CFG.language, course_id:CFG.course_id,''',
        '''    student_id:CFG.student_id, language:langBase(CFG.language), dialect:langDialect(CFG.language),
    course_id:CFG.course_id,''',
    ),
    # 3. browser voices: ar-EG asks for an Egyptian voice, ar-MSA for plain Arabic
    (
        '''  const want = (lang || 'en').toLowerCase();
  const exact = ttsVoices.filter(v => (v.lang || '').toLowerCase().startsWith(want));
  const pool = exact.length ? exact : ttsVoices.filter(v => (v.lang || '').toLowerCase().startsWith('en'));
  const list = pool.length ? pool : ttsVoices.slice();''',
        '''  const want = (lang || 'en').toLowerCase().replace('-msa', '');
  const base = langBase(lang);
  const exact = ttsVoices.filter(v => (v.lang || '').toLowerCase().startsWith(want));
  const pool = exact.length ? exact
             : ttsVoices.filter(v => (v.lang || '').toLowerCase().startsWith(base));
  const list = pool.length ? pool
             : ttsVoices.filter(v => (v.lang || '').toLowerCase().startsWith('en'));
  const finalists = list.length ? list : ttsVoices.slice();''',
    ),
    (
        '''  return list.sort((a, b) => score(b) - score(a))[0];''',
        '''  return finalists.sort((a, b) => score(b) - score(a))[0];''',
    ),
    (
        '''  const want = (CFG.language || 'en').toLowerCase();
  if(!TTS_OK) return { available:false, reason:'no speech synthesis in this browser' };''',
        '''  // `ar-MSA` has no browser voice of its own: judge it as plain Arabic.
  const want = (CFG.language || 'en').toLowerCase().replace('-msa', '');
  if(!TTS_OK) return { available:false, reason:'no speech synthesis in this browser' };''',
    ),
    (
        '''  const want = (CFG.language || 'en').toLowerCase();
  const keep = ttsVoice && (ttsVoice.lang || '').toLowerCase().startsWith(want);''',
        '''  const want = (CFG.language || 'en').toLowerCase().replace('-msa', '');
  const keep = ttsVoice && (ttsVoice.lang || '').toLowerCase().startsWith(want);''',
    ),
    # 4. adapt to what the service reports after a live switch
    (
        '''    if(e.to && /^[a-z]{2}$/i.test(e.to)) CFG.language = e.to.toLowerCase();
      $('langchip').textContent = e.to; toast('language → '+e.to);''',
        '''    if(e.dialect) CFG.language = e.dialect;                        // ar-EG / ar-MSA
      else if(e.to && /^[a-z]{2}(-[a-z]{2,3})?$/i.test(e.to)) CFG.language = e.to.toLowerCase();
      $('langchip').textContent = (CFG.languages[CFG.language] || e.to);
      toast('language → ' + (CFG.languages[CFG.language] || e.to));''',
    ),
    # 5. the select/chip shows the register, not just `ar`
    (
        '''    const wanted = sel.value, previous = CFG.language;
    CFG.language = wanted;
    $('langchip').textContent = CFG.languages[wanted]+' ('+wanted+')';''',
        '''    const wanted = sel.value, previous = CFG.language;
    CFG.language = wanted;
    $('langchip').textContent = CFG.languages[wanted] + ' (' + wanted + ')';
    applyVoiceForLanguage();''',
    ),
])

# the exports the Node harness builds against must include the new helpers
s = read("app/static/voice_mode.html")
assert "langBase" in s
print("voice screen patched")

# --------------------------------------------------------------------------- #
# topics page: the same two options when launching the voice screen
# --------------------------------------------------------------------------- #

sub("app/static/topics.html", [
    (
        '''function buildLanguages(){
  const sel = $('lang');
  LANGUAGES.forEach(l=>{
    const o = document.createElement('option');
    o.value = l.code;
    o.textContent = l.name + ' (' + l.code + ')' + (l.realtime_native ? '' : ' · composed pipeline');
    sel.appendChild(o);
  });''',
        '''function buildLanguages(){
  const sel = $('lang');
  // Arabic is offered as the two registers the service actually speaks
  // (app/voice/dialects.py): same lesson, different voice and wording. Every
  // other language is a plain code.
  const offering = [];
  LANGUAGES.forEach(l=>{
    if(l.code === 'ar'){
      offering.push({ code:'ar-EG', name:'العربية المصرية · Arabic (Egyptian)', native:l.realtime_native });
      offering.push({ code:'ar-MSA', name:'العربية الفصحى · Arabic (fusHa)', native:l.realtime_native });
      return;
    }
    offering.push({ code:l.code, name:l.name, native:l.realtime_native });
  });
  offering.forEach(l=>{
    const o = document.createElement('option');
    o.value = l.code;
    o.textContent = l.name + ' (' + l.code + ')' + (l.native ? '' : ' · composed pipeline');
    sel.appendChild(o);
  });''',
    ),
    (
        '''  const installed = tts.filter(v => (v.lang||'').toLowerCase().startsWith(l.code)).length;''',
        '''  const base = String(l.code || 'en').split('-')[0].toLowerCase();
  const installed = tts.filter(v => (v.lang||'').toLowerCase().startsWith(base)).length;''',
    ),
    (
        '''    language: lang,
    student: $('student').value.trim() || 'demo-student-001',''',
        '''    language: lang,
    student: $('student').value.trim() || 'demo-student-001',''',
    ),
], all_=True)
print("topics page patched")
