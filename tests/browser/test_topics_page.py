"""The topic picker page, exercised headlessly.

`/topics` builds its cards in the browser, so pytest cannot see them in the HTML.
This suite runs the page's real JavaScript in Node against a small DOM stub and
asserts the picker offers the whole catalogue, all ten languages, and that
starting a lesson produces the deep link the voice screen expects.

Skipped automatically when Node is not installed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "app" / "static" / "topics.html"

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

#: Minimal DOM + capture harness. Cards are collected as they are appended so the
#: test can read what the page would have drawn.
HARNESS = r"""
class El {
  constructor(tag){ this.tag = tag; this.children = []; this._html = ''; this.className = '';
    this.style = {}; this.classList = { add(){}, remove(){}, toggle(){} };
    this.value = ''; this.textContent = ''; this.checked = false; this.disabled = false;
    this.onclick = null; this.onchange = null; this.selected = false; this.title = ''; }
  appendChild(c){ this.children.push(c); return c; }
  addEventListener(){}
  set innerHTML(v){
    this._html = String(v);
    this.children = [];
    // A real browser parses this markup; the stub only needs the elements the
    // page immediately queries for.
    for(const cls of ['start', 'ghost']){
      const re = new RegExp('class="' + cls + '"', 'g');
      while(re.exec(this._html)){
        const child = new El('button');
        child.className = cls;
        this.children.push(child);
      }
    }
  }
  get innerHTML(){ return this._html; }
  querySelector(sel){
    const want = sel.replace('.', '');
    const found = this.children.find(c => c.className === want);
    if(found) return found;
    for(const c of this.children){ const inner = c.querySelector && c.querySelector(sel); if(inner) return inner; }
    return null;
  }
  get options(){ return this.children; }
}
const nodes = {};
function node(id){ return nodes[id] || (nodes[id] = new El('div')); }
global.document = {
  getElementById: (id)=> id === 'catalog' ? { textContent: require('fs').readFileSync(process.argv[3], 'utf8') } : node(id),
  createElement: (t)=> new El(t),
  querySelectorAll: ()=> [],
};
global.window = { speechSynthesis: { getVoices: ()=>[
  {name:'Google US English Natural', lang:'en-US'}, {name:'Amira', lang:'ar-EG'}], addEventListener(){} } };
const navigated = [];
global.location = { get href(){ return ''; }, set href(v){ navigated.push(v); } };
global.fetch = async ()=>({ json: async ()=>({status:'ok', service:'lerna-voice-ai'}) });
global.URLSearchParams = URLSearchParams;

require(require('path').resolve(process.argv[2]));

const out = { values: {}, checks: {} };
const courses = node('courses'), grid = node('grid'), langSel = node('lang');
out.values.courseButtons = courses.children.length;
out.values.topicCards = grid.children.length;
out.values.languageOptions = langSel.children.length;
out.values.languageValues = langSel.children.map(o => o.value);
out.values.heading = node('topicHeading').textContent;
out.values.statChip = node('statChip').textContent;
out.values.firstCardHtml = (grid.children[0] || {innerHTML:''}).innerHTML;

/* starting a lesson from the first card must produce the deep link */
const start = grid.children.length && grid.children[0].querySelector('.start');
if(start && start.onclick) start.onclick();
out.values.navigated = navigated.slice();

/* switching course rebuilds the topic list for that course */
courses.children[2] && courses.children[2].onclick && courses.children[2].onclick();
out.values.cardsAfterCourseSwitch = grid.children.length;
out.values.headingAfterCourseSwitch = node('topicHeading').textContent;

console.log('RESULT ' + JSON.stringify(out));
process.exit(0);
"""


@pytest.fixture(scope="module")
def picker(tmp_path_factory) -> dict:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        html = client.get("/topics").text
    block = re.search(r'<script id="catalog" type="application/json">(.*?)</script>', html, re.S)
    assert block, "the picker must embed the catalogue"
    js = re.search(r"<script>\n(.*?)</script>", html, re.S).group(1)

    tmp = tmp_path_factory.mktemp("picker")
    (tmp / "catalog.json").write_text(block.group(1))
    (tmp / "page.js").write_text(js)
    (tmp / "harness.js").write_text(HARNESS)
    proc = subprocess.run(
        ["node", str(tmp / "harness.js"), str(tmp / "page.js"), str(tmp / "catalog.json")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"node failed:\n{proc.stdout}\n{proc.stderr}"
    line = [l for l in proc.stdout.splitlines() if l.startswith("RESULT ")]
    assert line, f"no result:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(line[-1][len("RESULT ") :])["values"]


@requires_node
def test_picker_lists_courses_topics_and_languages(picker):
    assert picker["courseButtons"] == 5
    assert picker["topicCards"] == 5, "the first course's topics should be on screen"
    # The ten mandatory languages, one entry each, plus academic Egyptian Arabic
    # (`ar-eg`) as an eleventh, selectable register that rides on base `ar`.
    assert picker["languageOptions"] == 11
    assert picker["languageValues"] == ["en", "ar", "ar-eg", "fr", "sw", "am", "ha", "so", "yo", "ig", "zu"]
    assert "Algorithms" in picker["heading"]
    assert "5 courses · 22 topics · 88 lesson steps" in picker["statChip"]


@requires_node
def test_cards_show_the_lesson_steps(picker):
    html = picker["firstCardHtml"]
    assert "Binary Search" in html
    assert "The idea of halving" in html, "each card must preview its lesson plan"
    assert "Start lesson" in html


@requires_node
def test_starting_a_lesson_deep_links_the_voice_screen(picker):
    assert picker["navigated"], "clicking Start lesson must navigate"
    url = picker["navigated"][0]
    assert url.startswith("voice?"), url
    assert "topic_id=binary-search" in url
    assert "language=en" in url
    assert "autostart=1" in url


@requires_node
def test_switching_course_rebuilds_the_topics(picker):
    assert "Mechanics" in picker["headingAfterCourseSwitch"]
    assert picker["cardsAfterCourseSwitch"] == 4
