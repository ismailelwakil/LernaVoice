"""Round 17 UI: one Arabic entry, and it is fusHa.

Run once from the service root:  python3 tools/patch_arabic_ui_formal.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    write(path, s)


# --------------------------------------------------------------------------- #
# the voice screen: Arabic is back to one option - the formal one
# --------------------------------------------------------------------------- #

sub("app/static/voice_mode.html", [
    (
        '''  "languages": {"en":"English","ar-EG":"العربية المصرية · Arabic (Egyptian)",
    "ar-MSA":"العربية الفصحى · Arabic (fusHa)","fr":"Français","sw":"Kiswahili",''',
        '''  "languages": {"en":"English","ar":"العربية الفصحى · Arabic (fusHa)","fr":"Français","sw":"Kiswahili",''',
    ),
    (
        '''    <div class="hint"><b>Arabic has two registers:</b> <b>العربية المصرية</b> speaks with the
      Egyptian voice (<code>ar-EG-SalmaNeural</code>) and the Egyptian phrase set;
      <b>العربية الفصحى</b> speaks with the MSA voice (<code>ar-SA-ZariyahNeural</code>) and formal
      lines. Same lesson, same plan, same checkpoint — only the register changes, and you can
      switch between them mid-lesson.<br />
      Language switches the live lesson straight away — the tutor acknowledges''',
        '''    <div class="hint"><b>Arabic is taught in Modern Standard Arabic (fusHa)</b> — voice
      <code>ar-SA-ZariyahNeural</code> with formal lines and a lecture-style instruction. The
      language code stays <code>ar</code>, so routing, checkpoints and the English concept
      store are untouched.<br />
      Language switches the live lesson straight away — the tutor acknowledges''',
    ),
    (
        '''    if(e.dialect) CFG.language = e.dialect;                        // ar-EG / ar-MSA''',
        '''    if(e.dialect) CFG.language = langBase(e.to);                  // `ar` (fusHa)''',
    ),
])

# --------------------------------------------------------------------------- #
# the topic picker: one Arabic option again
# --------------------------------------------------------------------------- #

sub("app/static/topics.html", [
    (
        '''  // Arabic is offered as the two registers the service actually speaks
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
  offering.forEach(l=>{''',
        '''  // One entry per language. Arabic is taught in fusHa (app/voice/dialects.py);
  // `l.name` already carries that wording from the catalogue.
  LANGUAGES.forEach(l=>{''',
    ),
    (
        '''    o.textContent = l.name + ' (' + l.code + ')' + (l.native ? '' : ' · composed pipeline');''',
        '''    o.textContent = l.name + ' (' + l.code + ')'
                  + (l.realtime_native ? '' : ' · composed pipeline');''',
    ),
])
print("voice screen + topic picker: one formal Arabic option")
