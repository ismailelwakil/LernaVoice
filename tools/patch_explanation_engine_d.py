"""Round 19, part D: the demo surfaces show and control the level.

Run once from the service root:  python3 tools/patch_explanation_engine_d.py
"""
import io


def sub(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(s)


# --------------------------------------------------------------------------- #
# /topics: choose who the explanation is for, and carry it into the voice page
# --------------------------------------------------------------------------- #

sub("app/static/topics.html", [
    (
        """    <div class="field">
      <label for="returning">Returning student</label>""",
        """    <div class="field">
      <label for="explain">Explain for</label>
      <select id="explain">
        <option value="">student's profile</option>
        <option value="beginner">beginner</option>
        <option value="intermediate">intermediate</option>
        <option value="advanced">advanced</option>
      </select>
    </div>
    <div class="field">
      <label for="returning">Returning student</label>""",
    ),
    (
        """  const params = {
    topic_id: topic.id,
    language: lang,
    student: $('student').value.trim() || 'demo-student-001',
    returning: $('returning').value,
    autostart: '1',
  };""",
        """  const params = {
    topic_id: topic.id,
    language: lang,
    student: $('student').value.trim() || 'demo-student-001',
    returning: $('returning').value,
    autostart: '1',
  };
  // Empty = the level stored in the student's profile decides (see /voice/session).
  const level = $('explain').value; if(level) params.level = level;""",
    ),
    (
        """function openVoice(){
  location.href = url('voice', { language: $('lang').value, student: $('student').value.trim() || 'demo-student-001' });
}""",
        """function openVoice(){
  const params = { language: $('lang').value, student: $('student').value.trim() || 'demo-student-001' };
  const level = $('explain').value; if(level) params.level = level;
  location.href = url('voice', params);
}""",
    ),
    (
        '    with <code>POST /voice/session {{"topic_id": "…", "language": "…"}}</code>.',
        '    with <code>POST /voice/session {{"topic_id": "…", "language": "…", "level": "beginner"}}</code>.\n'
        "    The level shapes the explanation the tutor teaches from, not the syllabus: the same topic\n"
        "    and the same checkpoints, pitched for a beginner, an intermediate or an advanced student.",
    ),
])

# --------------------------------------------------------------------------- #
# /voice: accept ?level=, send it, and show what is being taught
# --------------------------------------------------------------------------- #

sub("app/static/voice_mode.html", [
    (
        """    <div class="kv"><i>Language</i><b id="d-lang">—</b></div>""",
        """    <div class="kv"><i>Language</i><b id="d-lang">—</b></div>
    <div class="kv"><i>Level</i><b id="d-level">—</b></div>
    <div class="kv"><i>Teaching order</i><b id="d-moves">—</b></div>
    <div class="kv"><i>Sources</i><b id="d-src">—</b></div>""",
    ),
    (
        """    lesson_id:CFG.lesson_id, topic:CFG.topic, topic_id:CFG.topic_id || null,
    resume_latest:CFG.resume_latest});""",
        """    lesson_id:CFG.lesson_id, topic:CFG.topic, topic_id:CFG.topic_id || null,
    level:CFG.level || null,
    resume_latest:CFG.resume_latest});""",
    ),
    (
        """  $('d-lang').textContent  = s.language;""",
        """  $('d-lang').textContent  = s.language;
  $('d-level').textContent = s.student_level || '—';
  const ex = s.explanation || {};
  const moves = ex.moves || [];
  $('d-moves').textContent = moves.length
    ? moves.map(m => m.kind === 'hook' ? 'picture' : m.kind).join(' › ') + '  (' + moves.length + ')'
    : '—';
  $('d-src').textContent   = (ex.sources||[]).map(x => x.publisher).join(', ') || '—';""",
    ),
    (
        """  const q = new URLSearchParams(location.search);
  const qTopic = q.get('topic_id');""",
        """  const q = new URLSearchParams(location.search);
  const qLevel = q.get('level');            // beginner | intermediate | advanced
  if(qLevel) CFG.level = qLevel;
  const qTopic = q.get('topic_id');""",
    ),
])

# --------------------------------------------------------------------------- #
# /console: pick the level at create, and switch it mid-lesson
# --------------------------------------------------------------------------- #

sub("app/static/console.html", [
    (
        """    <label style="margin-top:10px">
      <input type="checkbox" id="returning" style="width:auto" /> Returning student (recap)
    </label>""",
        """    <label>Level</label>
    <select id="lvl">
      <option value="">student's profile</option>
      <option value="beginner">beginner</option>
      <option value="intermediate">intermediate</option>
      <option value="advanced">advanced</option>
    </select>
    <label style="margin-top:10px">
      <input type="checkbox" id="returning" style="width:auto" /> Returning student (recap)
    </label>""",
    ),
    (
        """      <button id="btnLang" disabled>Switch language mid-lesson</button>
    </div>""",
        """      <button id="btnLang" disabled>Switch language mid-lesson</button>
    </div>
    <div class="bar">
      <select id="lvl2" style="flex:1">
        <option value="beginner">beginner</option>
        <option value="intermediate" selected>intermediate</option>
        <option value="advanced">advanced</option>
      </select>
      <button id="btnLevel" disabled>Re-pitch the explanation</button>
    </div>""",
    ),
    (
        """    topic:$('topic').value, resume_latest:$('returning').checked});""",
        """    topic:$('topic').value, level:$('lvl').value || null,
    resume_latest:$('returning').checked});""",
    ),
    (
        """  ['btnStart','btnInt','btnResume','btnPause','btnAsk','btnLang','btnEnd','btnState','btnMic']""",
        """  ['btnStart','btnInt','btnResume','btnPause','btnAsk','btnLang','btnLevel','btnEnd','btnState','btnMic']""",
    ),
    (
        """$('btnLang').onclick   = ()=>send({type:'language', language:$('lang2').value});""",
        """$('btnLang').onclick   = ()=>send({type:'language', language:$('lang2').value});
$('btnLevel').onclick  = async () => {
  const r = await jreq('POST','/voice/session/'+sid+'/level',{level:$('lvl2').value});
  if(r) log('level → '+r.detail+' (the checkpoint is untouched)','e-sess');
};""",
    ),
])
print("part D: level pickers on /topics, /voice (deep link + dev panel) and /console")
