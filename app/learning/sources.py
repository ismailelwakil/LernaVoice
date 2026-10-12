"""The trusted sources the tutor is allowed to teach from.

The student picks a topic from the course catalogue; the tutor then explains it
from **the course material plus the sources this service has chosen and vetted**,
never from whatever the model happens to remember. That is what makes an
explanation both easy to follow and safe to rely on.

Every topic therefore carries a small pack:

  * `sources` — real, named, linkable material (OpenStax, MIT OpenCourseWare,
    Nature Scitable, the official Python docs, Khan Academy, LibreTexts,
    HyperPhysics, NCBI Bookshelf, Paul's Online Math Notes). Each entry says who
    publishes it and *why it is trusted for this topic*, so a human can audit the
    choice instead of trusting a black box.
  * `items`   — the claims the tutor is allowed to teach (`fact`), plus the human
    scaffolding it explains them with: `analogy`, `example`, `pitfall`, `use` and
    `check` questions. Packs are curated in English, with Arabic wording for the
    topics the Arabic demo actually opens.

`TOPIC_SOURCES` is deliberately data, not code: replacing these with the LERNA
course's own material is an edit to this table, not to the tutor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    publisher: str
    kind: str  # open-textbook | course-notes | official-docs | reference | interactive
    url: str
    why: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "publisher": self.publisher,
            "kind": self.kind,
            "url": self.url,
            "why": self.why,
        }


@dataclass(frozen=True)
class Item:
    """One teaching item: an allowed claim, or the words used to make it land."""

    kind: str  # fact | analogy | example | pitfall | use | check
    en: str
    ar: str = ""
    #: Which lesson part this belongs to (1-based, matching the plan's order).
    #: 0 = belongs to the topic as a whole (checks). Sectioned items let a pass
    #: teach its own part properly instead of spreading a few facts across the
    #: whole lesson — see `app/learning/lesson_script.py`.
    section: int = 0

    def text(self, language: str) -> str:
        if language == "ar" and self.ar:
            return self.ar
        return self.en

    def as_dict(self, language: str = "en") -> dict[str, str]:
        return {
            "kind": self.kind,
            "text": self.text(language),
            "english": self.en,
            "section": self.section,
        }


@dataclass(frozen=True)
class TopicPack:
    topic_id: str
    sources: tuple[Source, ...] = field(default_factory=tuple)
    items: tuple[Item, ...] = field(default_factory=tuple)

    def of(self, kind: str) -> tuple[Item, ...]:
        return tuple(i for i in self.items if i.kind == kind)

    def first(self, kind: str) -> Item | None:
        found = self.of(kind)
        return found[0] if found else None

    def as_dict(self, language: str = "en") -> dict:
        return {
            "topic_id": self.topic_id,
            "sources": [s.as_dict() for s in self.sources],
            "items": [i.as_dict(language) for i in self.items],
        }


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _slug(text: str, length: int = 36) -> str:
    keep = "".join(ch if ch.isalnum() or ch == " " else " " for ch in text.lower())
    return "-".join(keep.split())[:length].strip("-") or "source"


def _s(title: str, publisher: str, kind: str, url: str, why: str) -> Source:
    return Source(
        id="src-" + _slug(title),
        title=title,
        publisher=publisher,
        kind=kind,
        url=url,
        why=why,
    )


def _i(kind: str, en: str, ar: str = "", section: int = 0) -> Item:
    return Item(kind=kind, en=en, ar=ar, section=section)


#: The vetted catalogue, by publisher — one place to review what the tutor may cite.
OCW = ("MIT OpenCourseWare", "course-notes", "ocw.mit.edu")
OPENSTAX_CALC = ("OpenStax Calculus Volume 1", "open-textbook", "openstax.org/details/books/calculus-volume-1")
PAULS = ("Paul's Online Math Notes", "course-notes", "tutorial.math.lamar.edu")
KHAN = ("Khan Academy", "reference", "khanacademy.org")
OPENSTAX_PHYS = ("OpenStax College Physics 2e", "open-textbook", "openstax.org/details/books/college-physics-2e")
HYPER = ("HyperPhysics (Georgia State University)", "reference", "hyperphysics.phy-astr.gsu.edu")
PHET = ("PhET Interactive Simulations (CU Boulder)", "interactive", "phet.colorado.edu")
OPENSTAX_BIO = ("OpenStax Biology 2e", "open-textbook", "openstax.org/details/books/biology-2e")
SCITABLE = ("Nature Scitable", "reference", "nature.com/scitable")
NCBI = ("NCBI Bookshelf", "reference", "ncbi.nlm.nih.gov/books")
PYDOCS = ("The Python Tutorial (python.org)", "official-docs", "docs.python.org/3/tutorial")
PYSTD = ("The Python Standard Library (python.org)", "official-docs", "docs.python.org/3/library")
MDN = ("MDN Web Docs", "reference", "developer.mozilla.org")
ATBS = ("Automate the Boring Stuff with Python", "reference", "automatetheboringstuff.com")


def _src(entry: tuple[str, str, str], *, why: str, path: str = "") -> Source:
    title, kind, host = entry
    url = f"https://{host}/{path.lstrip('/')}" if path else f"https://{host}/"
    return _s(title, title.split(" (")[0], kind, url, why)


# --------------------------------------------------------------------------- #
# the packs
# --------------------------------------------------------------------------- #

ALGO_WHY = "MIT's own introductory algorithms course — the same material this lesson follows."

TOPIC_SOURCES: dict[str, TopicPack] = {
    # ---------------------------------------------------------------- algorithms
    "binary-search": TopicPack(
        topic_id="binary-search",
        sources=(
            _src(OCW, why=ALGO_WHY, path="courses/6-006-introduction-to-algorithms-spring-2020/"),
            _src(KHAN, why="Short worked searches that match the plan's examples.", path="computing/computer-science/algorithms"),
            _s("bisect — Array bisection algorithm", "Python Software Foundation", "official-docs",
               "https://docs.python.org/3/library/bisect.html",
               "The standard library's own binary search: shows the exact midpoint arithmetic."),
        ),
        items=(
            # --- 1. The idea of halving --------------------------------------
            _i("analogy", "Think of looking a word up in a dictionary: open the middle, decide which half it must be in, repeat.",
               "تخيّل أنك تبحث عن كلمة في المعجم: افتح المنتصف، ثم اختر النصف الذي يجب أن تكون فيه الكلمة، وأعد الخطوة.", 1),
            _i("fact", "It needs one thing and one thing only: the data is sorted, so a single comparison with the middle tells you which half can be thrown away.",
               "لا يحتاج إلا شيئًا واحدًا فقط: أن تكون البيانات مرتبة، فتكفي مقارنة واحدة بالعنصر الأوسط لتعرف أي نصف يمكن استبعاده.", 1),
            _i("fact", "It looks at the middle element of a sorted list and discards the half that cannot contain the target.",
               "ينظر إلى العنصر الأوسط في قائمة مرتبة، ثم يستبعد النصف الذي يستحيل أن يحتوي على الهدف.", 1),
            _i("fact", "Sorted order is not a detail, it is the whole assumption: comparing with the middle says nothing at all while the data is unordered.",
               "الترتيب ليس تفصيلًا، بل هو الشرط كله: مقارنة العنصر الأوسط لا تقول شيئًا على بيانات غير مرتبة.", 1),
            _i("fact", "Because every comparison removes half the candidates, the part still in play shrinks by half at every step.",
               "ولأن كل مقارنة تستبعد نصف المرشحين، فإن الجزء الذي ما زال قيد البحث ينكمش إلى النصف في كل خطوة.", 1),
            _i("fact", "That is the whole difference from looking at the items one by one: a plain search can only throw away the item it just checked, while this one throws away everything on the wrong side of the middle at once.",
               "وهذا هو الفرق كله عن البحث عنصرًا عنصرًا: البحث العادي يستبعد العنصر الذي فحصه فقط، بينما هذا يستبعد كل ما يقع في الجهة الخطأ من المنتصف دفعة واحدة.", 1),
            # --- 2. Trace it on a small array --------------------------------
            _i("fact", "You carry two markers, low and high; everything between them is what is still in play.",
               "تحمل معك مؤشرين: الأدنى low والأعلى high، وكل ما بينهما هو ما زال قيد البحث.", 2),
            _i("fact", "One step is always the same three moves: compute the middle, compare with it, then move one marker past it.",
               "والخطوة الواحدة ثلاث حركات ثابتة: احسب المنتصف، قارن به، ثم حرّك أحد المؤشرين بعيدًا عنه.", 2),
            _i("example", "In [2, 5, 8, 12, 16, 23, 38], searching for 23: the middle is 12, so go right; the middle is now 23 and we are done.",
               "في المصفوفة [2، 5، 8، 12، 16، 23، 38] نبحث عن 23: المنتصف 12، فنذهب إلى اليمين؛ يصبح المنتصف 23 وننتهي.", 2),
            _i("example", "Searching for 5 in the same array: the middle 12 sends us left, and the middle of that half is 5 — found in two comparisons.",
               "وللبحث عن 5 في المصفوفة نفسها: العنصر الأوسط 12 يوجّهنا إلى اليسار، ووسط ذلك النصف هو 5 — وجدناه بمقارنتين.", 2),
            _i("fact", "The midpoint is written low + (high - low) // 2, not (low + high) // 2, so adding the two ends cannot overflow.",
               "تُحسب نقطة المنتصف بالصيغة low + (high - low) // 2 وليس (low + high) // 2 حتى لا يتجاوز جمع الطرفين حدود الأعداد الصحيحة.", 2),
            # --- 3. Why the cost is logarithmic ------------------------------
            _i("fact", "Each step halves the range, so a million items need about twenty comparisons.",
               "كل خطوة تنصّف المدى، فمليون عنصر تحتاج نحو عشرين مقارنة.", 3),
            _i("fact", "Doubling the amount of data adds exactly one comparison — it never doubles the work.",
               "ومضاعفة حجم البيانات تضيف مقارنة واحدة فقط، ولا تضاعف العمل أبدًا.", 3),
            _i("fact", "Sixteen sorted items take at most four comparisons; thirty-two take at most five.",
               "ستة عشر عنصرًا مرتبًا تحتاج أربع مقارنات على الأكثر، واثنان وثلاثون تحتاج خمسًا على الأكثر.", 3),
            _i("use", "sorted indexes, database key lookups and version lists are all built on it.",
               "الفهارس المرتبة، والبحث بمفاتيح قواعد البيانات، وقوائم الإصدارات: كلها مبنية عليه.", 3),
            # --- 4. Common mistakes ------------------------------------------
            _i("pitfall", "Running it on an unsorted list: discarding a half is only valid when the data is ordered.",
               "تشغيله على مصفوفة غير مرتبة: استبعاد نصف المجال لا يصح إلا إذا كانت البيانات مرتبة.", 4),
            _i("pitfall", "On very large arrays (low + high) // 2 can overflow, which is exactly what the low + (high - low) // 2 form avoids.",
               "في المصفوفات الضخمة قد يتجاوز (low + high) // 2 حدود الأعداد الصحيحة، وهذا تحديدًا ما تتجنبه صيغة low + (high - low) // 2.", 4),
            _i("pitfall", "Carrying on after low passes high: at that moment the target is simply not in the array and the loop must end.",
               "الاستمرار بعد أن يتجاوز low قيمة high: في تلك اللحظة يكون العنصر غير موجود في المصفوفة، ولا بد أن تتوقف الحلقة.", 4),
            _i("fact", "The dictionary picture breaks if you reshuffle the pages between lookups: the ordering is what this method trades on.",
               "تشبيه المعجم ينكسر إذا أعدت ترتيب الصفحات بين كل بحث وآخر: الترتيب هو ما تتاجر به هذه الطريقة.", 4),
            _i("check", "Which half do we keep after comparing with the middle?",
               "أي نصف نُبقي عليه بعد المقارنة بالعنصر الأوسط؟"),
            _i("check", "How many steps would 32 sorted items need at most?",
               "كم خطوة تحتاج 32 عنصرًا مرتبًا في أسوأ الحالات؟"),
            _i("check", "Why does halving the range make the number of steps logarithmic?",
               "لماذا يجعل تنصيف المدى عدد الخطوات لوغاريتميًا؟"),
        ),
    ),
    "merge-sort": TopicPack(
        topic_id="merge-sort",
        sources=(
            _src(OCW, why=ALGO_WHY, path="courses/6-006-introduction-to-algorithms-spring-2020/"),
            _src(KHAN, why="Merge sort is walked through step by step with the same halving picture.", path="computing/computer-science/algorithms"),
            _s("OpenDSA Data Structures and Algorithms", "Virginia Tech", "course-notes",
               "https://opendsa-server.cs.vt.edu/",
               "An open textbook used in university algorithms courses; merge sort is derived, not asserted."),
        ),
        items=(
            _i("fact", "Merge sort splits the list in half, sorts each half the same way, then merges the two sorted halves.",
               "ترتيب الدمج يقسم القائمة نصفين، ويرتّب كل نصف بالطريقة نفسها، ثم يدمج النصفين المرتبين."),
            _i("fact", "Merging two sorted halves is linear: repeatedly take the smaller of the two front elements.",
               "دمج نصفين مرتبين خطّي: نأخذ الأصغر من بين أول عنصرين في كل نصف."),
            _i("fact", "It always costs n log n comparisons, is stable, and needs extra memory of order n.",
               "يكلّف دائمًا n لوغاريتم n مقارنة، وهو مستقر، لكنه يحتاج ذاكرة إضافية بمقدار n."),
            _i("analogy", "Two friends each sort a pile of cards, then you merge the piles by always taking the smaller top card.",
               "تخيّل صديقين يرتّب كل واحد كومة أوراق، ثم تدمج الكومتين بأخذ الورقة الأصغر من الأعلى في كل مرة."),
            _i("example", "Splitting [38, 27, 43, 3] gives [38, 27] and [43, 3]; each becomes sorted ([27, 38], [3, 43]); merging them gives [3, 27, 38, 43].",
               "تقسيم [38، 27، 43، 3] يعطي [38، 27] و[43، 3]؛ يصبح كل نصف مرتبًا؛ ثم ينتج الدمج [3، 27، 38، 43]."),
            _i("pitfall", "Forgetting the leftover elements: when one half runs out, the rest of the other half is copied as it is.",
               "نسيان العناصر المتبقية: عند انتهاء نصف، يُنقل باقي النصف الآخر كما هو."),
            _i("use", "you need predictable worst-case time, or a stable sort, or you are sorting a linked list.",
               "تحتاج زمنًا مضمونًا في أسوأ الحالات، أو ترتيبًا مستقرًا، أو ترتّب قائمة مترابطة."),
            _i("check", "What is the base case, the piece so small it is already sorted?",
               "ما الحالة الأساسية، أي الجزء الصغير الذي يكون مرتبًا أصلًا؟"),
            _i("check", "How many comparisons does merging 8 items take?",
               "كم مقارنة يحتاج دمج ثمانية عناصر؟"),
            _i("check", "Why is the recursion depth logarithmic even though every level does linear work?",
               "لماذا يكون عمق الاستدعاء لوغاريتميًا رغم أن كل مستوى يكلّف زمنًا خطيًا؟"),
        ),
    ),
    "recursion": TopicPack(
        topic_id="recursion",
        sources=(
            _s("Structure and Interpretation of Computer Programs", "MIT Press", "textbook",
               "https://mitpress.mit.edu/9780262510875/structure-and-interpretation-of-computer-programs/",
               "The classic MIT text on recursive thinking and the substitution model."),
            _src(MDN, why="A short, precise definition with worked JavaScript examples.", path="en-US/docs/Web/JavaScript/Guide/Functions"),
            _src(OCW, why=ALGO_WHY, path="courses/6-006-introduction-to-algorithms-spring-2020/"),
        ),
        items=(
            _i("fact", "Every recursion needs a base case that stops it, and a recursive case that makes the problem smaller.",
               "كل استدعاء ذاتي يحتاج حالة أساسية توقفه، وحالة تكرارية تصغّر المسألة."),
            _i("fact", "Each call keeps its own copy of the variables on the call stack, so the stack grows with the depth.",
               "كل استدعاء يحتفظ بنسخته من المتغيرات على مكدّس الاستدعاءات، فينمو المكدّس مع العمق."),
            _i("fact", "Because the problem shrinks each time, the number of steps is usually logarithmic or linear in the input.",
               "لأن المسألة تصغر في كل مرة، يكون عدد الخطوات عادةً لوغاريتميًا أو خطيًا بالنسبة للمدخل."),
            _i("analogy", "Russian dolls: to open the smallest one you must open the ones around it first, then close them again on the way back.",
               "تخيّل الدمى الروسية: لتصل إلى الدمية الصغرى تفتح التي حولها أولًا، ثم تغلقها بالترتيب العكسي."),
            _i("example", "Factorial: 4! = 4 × 3!, and 1! = 1 stops the sequence.",
               "مثال المضروب: 4! = 4 × 3!، وتوقفها 1! = 1."),
            _i("pitfall", "Missing or unreachable base case: the calls never stop and the stack overflows.",
               "حالة أساسية ناقصة أو لا يمكن الوصول إليها: لا تتوقف الاستدعاءات ويفيض المكدّس."),
            _i("use", "the structure of the data is itself recursive — trees, nested lists, divide-and-conquer algorithms.",
               "تكون بنية البيانات نفسها تكرارية — أشجار أو قوائم متداخلة أو خوارزميات تقسيم وغلبة."),
            _i("check", "Which line stops the recursion?",
               "أي سطر يوقف الاستدعاء الذاتي؟"),
            _i("check", "What happens to the stack when the base case is missing?",
               "ماذا يحدث للمكدّس عند غياب الحالة الأساسية؟"),
            _i("check", "When is a loop clearer than recursion, and why?",
               "متى تكون الحلقة أوضح من الاستدعاء الذاتي، ولماذا؟"),
        ),
    ),
    "hash-tables": TopicPack(
        topic_id="hash-tables",
        sources=(
            _s("Introduction to Algorithms, 4th edition", "MIT Press", "textbook",
               "https://mitpress.mit.edu/9780262046305/introduction-to-algorithms/",
               "The standard reference: hashing, collisions and load factor are treated rigorously here."),
            _src(PYDOCS, why="Python's dict is the hash table the student will actually use.",
                 path="3/tutorial/datastructures.html#dictionaries"),
            _src(OCW, why=ALGO_WHY, path="courses/6-006-introduction-to-algorithms-spring-2020/"),
        ),
        items=(
            _i("fact", "A hash function turns a key into a bucket index, which is why lookups take constant time on average.",
               "دالة التجزئة تحوّل المفتاح إلى رقم خانة، ولذلك يكون البحث ثابت الزمن في المتوسط."),
            _i("fact", "Collisions are handled by chaining (a list per bucket) or open addressing (probe for the next free slot).",
               "تُعالج التعارضات بالتسلسل (قائمة لكل خانة) أو بالعنونة المفتوحة (البحث عن خانة فارغة تالية)."),
            _i("fact", "When the load factor grows the table is resized and the keys are rehashed, which is why a single insert can be slow.",
               "عند ارتفاع معامل الحِمل يُعاد تحجيم الجدول وتجزئة المفاتيح، ولذلك قد تكون إضافة واحدة بطيئة أحيانًا."),
            _i("analogy", "A cloakroom: your ticket number sends you straight to one hook instead of searching every coat.",
               "تخيّل غرفة معاطف: رقم تذكرتك يدلّك مباشرة على المكان المخصص."),
            _i("example", "Storing names by first letter: 'Mona' goes to the M bucket, so you never scan the A–L buckets.",
               "تخزين الأسماء بالحرف الأول: يذهب «Mona» إلى خانة الحرف M، فلا تفحص الخانات الأخرى."),
            _i("pitfall", "Using a mutable object as a key: if the key changes, its bucket no longer matches and the value is lost.",
               "استخدام كائن قابل للتغيير كمفتاح: إذا تغيّر المفتاح فلن تتوافق خانته، وتضيع القيمة."),
            _i("use", "you need to look something up by name, count occurrences, or cache results.",
               "تحتاج البحث بالاسم، أو عدّ التكرارات، أو تخزين نتائج سابقة."),
            _i("check", "What decides which bucket a key goes into?",
               "ما الذي يحدّد خانة المفتاح؟"),
            _i("check", "Two keys land in the same bucket — what are your two options?",
               "مفتاحان يقَعان في الخانة نفسها — ما الحلّان المتاحان؟"),
            _i("check", "Why is the average lookup constant time while the worst case is not?",
               "لماذا يكون البحث ثابت الزمن في المتوسط وليس في أسوأ الحالات؟"),
        ),
    ),
    "graph-bfs": TopicPack(
        topic_id="graph-bfs",
        sources=(
            _src(OCW, why=ALGO_WHY, path="courses/6-006-introduction-to-algorithms-spring-2020/"),
            _src(KHAN, why="Breadth-first search is animated level by level.", path="computing/computer-science/algorithms"),
            _s("Introduction to Algorithms, 4th edition", "MIT Press", "textbook",
               "https://mitpress.mit.edu/9780262046305/introduction-to-algorithms/",
               "BFS and shortest paths in unweighted graphs, proven rather than illustrated."),
        ),
        items=(
            _i("fact", "Breadth-first search explores a graph in rings: every neighbour of the start, then their neighbours.",
               "البحث بعرض الشجرة يستكشف الرسم في حلقات: كل جيران نقطة البداية، ثم جيرانهم."),
            _i("fact", "It uses a queue (first in, first out), which is exactly what keeps the rings in order.",
               "يستخدم طابورًا (الأول دخولًا أول خروجًا)، وهذا هو ما يحفظ ترتيب الحلقات."),
            _i("fact", "In an unweighted graph the first time BFS reaches a node is the shortest path to it, and the whole search costs O(V + E).",
               "في رسم غير موزون تكون أول مرة يصل فيها البحث إلى العقدة هي أقصر مسار إليها، وتكلفة البحث الكاملة O(V + E)."),
            _i("analogy", "Ripples from a stone in a pond: the wave reaches everything at distance one, then distance two.",
               "تخيّل تموجات حجر في ماء: تصل الموجة إلى كل ما يبعد خطوة واحدة، ثم خطوتين."),
            _i("example", "In a friendship graph, BFS finds the fewest introductions between you and a stranger.",
               "في رسم صداقات، يجد هذا البحث أقل عدد وسائط بينك وبين شخص لا تعرفه."),
            _i("pitfall", "Not marking nodes as visited: the queue fills with the same node forever.",
               "عدم تعليم العقد كمزارة: يمتلئ الطابور بالعقدة نفسها بلا نهاية."),
            _i("use", "you want the shortest number of steps in an unweighted network — routes, degrees of separation, puzzles.",
               "تريد أقصر عدد خطوات في شبكة غير موزونة — الطرق أو درجات الانفصال أو الألغاز."),
            _i("check", "What data structure keeps BFS in rings?",
               "ما بنية البيانات التي تحفظ ترتيب الحلقات؟"),
            _i("check", "Why must a node be marked the moment it is queued, not when it is visited?",
               "لماذا تُعلَّم العقدة لحظة إضافتها للطابور لا عند زيارتها؟"),
            _i("check", "Why does BFS stop being shortest-path once edges have weights?",
               "لماذا يتوقف هذا البحث عن إعطاء أقصر مسار عند وجود أوزان للحواف؟"),
        ),
    ),
    # ------------------------------------------------------------------ calculus
    "limits": TopicPack(
        topic_id="limits",
        sources=(
            _src(OPENSTAX_CALC, why="Peer-reviewed open calculus textbook used in university courses.", path=""),
            _src(PAULS, why="Long-standing university course notes; limit techniques in the order they are taught.", path=""),
            _src(KHAN, why="Short videos and practice that match the textbook examples.", path="math/calculus-1"),
        ),
        items=(
            _i("fact", "A limit is the value the function approaches as the input gets close to a point — not necessarily the value there.",
               "النهاية هي القيمة التي تقترب إليها الدالة عندما يقترب المدخل من نقطة معينة، وليس بالضرورة قيمة الدالة عند تلك النقطة."),
            _i("fact", "A limit can exist where the function is undefined or defined differently, which is why hole cases matter.",
               "قد توجد النهاية حيث تكون الدالة غير معرّفة أو معرّفة بقيمة مختلفة، ولذلك تهمّ حالات الفجوة."),
            _i("fact", "For a two-sided limit to exist, the left-hand and right-hand limits must agree.",
               "لكي توجد النهاية من الاتجاهين، يجب أن تتوافق النهاية من اليسار مع النهاية من اليمين."),
            _i("analogy", "Walking towards a step: you can approach it from either side and see the height it aims at, even if the step itself is missing.",
               "تخيّل أنك تمشي نحو درجة: يمكنك الاقتراب من أي جانب وترى الارتفاع المقصود، حتى لو كانت الدرجة نفسها غائبة."),
            _i("example", "(x² − 1)/(x − 1) is undefined at x = 1, yet its limit there is 2 because it simplifies to x + 1.",
               "الدالة (x² − 1)/(x − 1) غير معرّفة عند x = 1، ومع ذلك نهايتها هناك 2 لأنها تُبسّط إلى x + 1."),
            _i("pitfall", "Substituting the value first: if it gives 0/0 the expression must be simplified before substituting again.",
               "التعويض المباشر أولًا: إذا نتج 0/0 فيجب تبسيط المقدار قبل التعويض مرة أخرى."),
            _i("use", "you need the behaviour of a function where you cannot simply plug in the number — derivatives and series both start here.",
               "تحتاج سلوك الدالة حيث لا يمكن التعويض المباشر — والمشتقات والمتسلسلات تبدأ من هنا."),
            _i("check", "Does the function's value at the point decide its limit?",
               "هل تحدّد قيمة الدالة عند النقطة نهايتها؟"),
            _i("check", "What do the two one-sided limits have to do for the limit to exist?",
               "ماذا يجب أن يحدث للنهايتين من اليسار واليمين حتى توجد النهاية؟"),
            _i("check", "Why does the limit exist at a removable hole, and what does that say about continuity?",
               "لماذا توجد النهاية عند فجوة قابلة للإزالة، وماذا يعني ذلك عن الاتصال؟"),
        ),
    ),
    "derivatives": TopicPack(
        topic_id="derivatives",
        sources=(
            _src(OPENSTAX_CALC, why="Peer-reviewed open calculus textbook used in university courses."),
            _src(PAULS, why="Course notes that define the derivative as a limit and drill it."),
            _src(KHAN, why="Derivative rules illustrated on graphs.", path="math/calculus-1"),
        ),
        items=(
            _i("fact", "The derivative is the instantaneous rate of change — the slope of the tangent line at a point.",
               "المشتقة هي معدل التغير اللحظي — ميل خط المماس عند نقطة."),
            _i("fact", "It is defined as the limit of the difference quotient, which is why limits come first.",
               "تُعرَّف كنهاية حاصل الفرق، ولهذا تُدرَّس النهايات قبلها."),
            _i("fact", "Its sign tells you whether the function is rising or falling, and the derivative is zero at local extremes.",
               "إشارتها تدلّ على صعود الدالة أو هبوطها، وتكون صفرًا عند القيم المتطرفة المحلية."),
            _i("analogy", "A speedometer: the odometer shows how far you have gone, the speedometer shows how fast right now.",
               "تخيّل عدّاد السرعة: العدّاد الكلي يبيّن المسافة، وعدّاد السرعة يبيّن معدل التغير الآن."),
            _i("example", "For s(t) = t², the average speed between 2 and 2.1 seconds is 4.1 m/s, and the instantaneous speed at t = 2 is 4 m/s.",
               "للمسافة s(t) = t²، متوسط السرعة بين 2 و2.1 ثانية هو 4.1 م/ث، والسرعة اللحظية عند t = 2 هي 4 م/ث."),
            _i("pitfall", "Reading the derivative as a value of the function: f'(x) is a slope, not a height.",
               "قراءة المشتقة كقيمة للدالة: المشتقة ميل وليست ارتفاعًا."),
            _i("use", "you care about rates — motion, growth, marginal cost — or need maxima and minima.",
               "تهتم بالمعدلات — الحركة أو النمو أو التكلفة الحدية — أو تحتاج القيم العظمى والصغرى."),
            _i("check", "Does the derivative give a height or a slope?",
               "هل تعطي المشتقة ارتفاعًا أم ميلًا؟"),
            _i("check", "What does a zero derivative tell you about the graph?",
               "ماذا يخبرك كون المشتقة صفرًا عن المنحنى؟"),
            _i("check", "Why can a function be continuous but not differentiable at a corner?",
               "لماذا قد تكون الدالة متصلة وغير قابلة للاشتقاق عند زاوية؟"),
        ),
    ),
    "chain-rule": TopicPack(
        topic_id="chain-rule",
        sources=(
            _src(OPENSTAX_CALC, why="The chain rule is stated and proved as the derivative of a composition."),
            _src(PAULS, why="Step-by-step chain-rule drills in the order they are examined."),
            _src(KHAN, why="Worked composite-function examples.", path="math/calculus-1"),
        ),
        items=(
            _i("fact", "The chain rule differentiates a function inside a function: the derivative of the outside times the derivative of the inside."),
            _i("fact", "It is what lets you differentiate (3x + 1)⁵ or sin(x²) without expanding anything."),
            _i("fact", "As a rate statement: if y changes twice as fast as u, and u three times as fast as x, then y changes six times as fast as x."),
            _i("analogy", "Geared wheels: one turn of the first wheel turns the second three times, and the second turns the third twice — so the first turns the third six times."),
            _i("example", "For y = (3x + 1)⁵ the outside is u⁵ and the inside is 3x + 1, so dy/dx = 5(3x + 1)⁴ × 3."),
            _i("pitfall", "Forgetting the inside derivative — the single most common lost mark in this topic."),
            _i("use", "any nested expression, or a quantity whose rate depends on another changing quantity."),
            _i("check", "What are the two factors in the chain rule?"),
            _i("check", "Differentiate (3x + 1)⁵ — what is the inside derivative?"),
            _i("check", "Why does the chain rule follow from the limit definition of the derivative?"),
        ),
    ),
    "optimization": TopicPack(
        topic_id="optimization",
        sources=(
            _src(OPENSTAX_CALC, why="Applications of derivatives: maxima, minima and applied optimisation problems."),
            _src(PAULS, why="The standard recipe for optimisation word problems."),
            _src(OCW, why="MIT's single-variable calculus course covers constrained optimisation.", path="courses/18-01sc-single-variable-calculus-fall-2010/"),
        ),
        items=(
            _i("fact", "The candidates for a maximum or minimum are where the derivative is zero, where it does not exist, and the ends of the interval."),
            _i("fact", "A sign change of the derivative, or the second derivative, decides which candidate is a maximum and which is a minimum."),
            _i("fact", "In word problems the hard part is the setup: write the quantity to optimise in terms of one variable using the constraint."),
            _i("analogy", "Finding the highest point of a hill path: you stop walking uphill exactly where the ground flattens."),
            _i("example", "Fencing 40 m of fence into a rectangle of maximum area: area A = x(20 − x), and A' = 0 gives x = 10, a square."),
            _i("pitfall", "Forgetting the endpoints: on a closed interval the largest value can occur at the boundary, not at a flat point."),
            _i("use", "you must make something as large or as small as possible under a constraint — cost, area, time."),
            _i("check", "Which three kinds of point must be checked?"),
            _i("check", "In the fence example, why is the best rectangle a square?"),
            _i("check", "Why is a zero second derivative inconclusive, and what do you do then?"),
        ),
    ),
    # ------------------------------------------------------------------- physics
    "newton-laws": TopicPack(
        topic_id="newton-laws",
        sources=(
            _s("OpenStax College Physics 2e, Ch. 4 — Dynamics: Force and Newton's Laws of Motion",
               "OpenStax (Rice University)", "open-textbook",
               "https://openstax.org/details/books/college-physics-2e",
               "Peer-reviewed university physics text; every law is stated with its conditions."),
            _src(HYPER, why="Conceptual physics reference from Georgia State University, with the free-body diagrams."),
            _src(OCW, why="MIT's classical mechanics course, including the third law's subtleties.",
                 path="courses/8-01sc-classical-mechanics-fall-2016/"),
        ),
        items=(
            _i("fact", "An object keeps its velocity unless a net external force acts on it — constant velocity is not the same as zero force being 'used up'."),
            _i("fact", "The net force equals mass times acceleration, so the same force accelerates a lighter object more."),
            _i("fact", "Forces always come in equal and opposite pairs acting on two different bodies, which is why the pair never cancels."),
            _i("analogy", "Standing in a bus that brakes: your body keeps moving forward because no force has stopped it yet."),
            _i("example", "A 2 kg block pushed with 10 N accelerates at 5 m/s²; doubling the mass halves the acceleration."),
            _i("pitfall", "Putting the action and reaction forces on the same object, then concluding nothing can ever move."),
            _i("use", "you want to predict motion from the forces on an object — free-body diagram first, then sum the forces."),
            _i("check", "If the forces on an object cancel, what is its acceleration?"),
            _i("check", "Where does the reaction force act, and why does that matter?"),
            _i("check", "Why do the laws only hold in an inertial frame?"),
        ),
    ),
    "projectile-motion": TopicPack(
        topic_id="projectile-motion",
        sources=(
            _s("OpenStax College Physics 2e, Ch. 3 — Two-Dimensional Kinematics",
               "OpenStax (Rice University)", "open-textbook",
               "https://openstax.org/details/books/college-physics-2e",
               "Peer-reviewed university physics text; projectile equations derived from the independence of the axes."),
            _src(HYPER, why="Trajectory analysis with the algebra worked out."),
            _s("Projectile Motion", "PhET Interactive Simulations (CU Boulder)", "interactive",
               "https://phet.colorado.edu/en/simulations/projectile-motion",
               "Change the angle and speed and watch the trajectory — the fastest way to build intuition."),
        ),
        items=(
            _i("fact", "Horizontal and vertical motion are independent: gravity changes only the vertical velocity."),
            _i("fact", "The horizontal velocity stays constant (ignoring air resistance), so horizontal distance is that speed times time."),
            _i("fact", "The vertical motion is uniformly accelerated with a = −g, which is why the range peaks at a 45° launch angle."),
            _i("analogy", "Throw a ball forward while dropping another straight down: both hit the floor at the same moment."),
            _i("example", "A ball thrown at 20 m/s at 30° has a vertical initial speed of 10 m/s, so it rises for about one second."),
            _i("pitfall", "Mixing the axes: using a single velocity for both, or putting acceleration into the horizontal direction."),
            _i("use", "any launch problem — sports, ballistics without air resistance, falling objects with a push."),
            _i("check", "Which direction does gravity change the velocity in?"),
            _i("check", "Why does the ball thrown forward land at the same time as the dropped one?"),
            _i("check", "Why does ignoring air resistance break down at high speeds and long flights?"),
        ),
    ),
    "energy-conservation": TopicPack(
        topic_id="energy-conservation",
        sources=(
            _s("OpenStax College Physics 2e, Ch. 7 — Work, Energy and Energy Resources",
               "OpenStax (Rice University)", "open-textbook",
               "https://openstax.org/details/books/college-physics-2e",
               "Peer-reviewed textbook with worked energy examples and the conservation statement."),
            _src(HYPER, why="Roller-coaster style energy conversions worked out step by step."),
            _src(OCW, why="MIT 8.01 develops work and energy from Newton's laws.", path="courses/8-01sc-classical-mechanics-fall-2016/"),
        ),
        items=(
            _i("fact", "Mechanical energy is conserved when only conservative forces (like gravity) do work."),
            _i("fact", "Work done by the net force equals the change in kinetic energy — that is the work-energy theorem."),
            _i("fact", "Energy is transformed, not created: losing height converts into speed, friction converts it into heat."),
            _i("analogy", "A roller coaster: at the top of the hill the energy is stored as height, at the bottom as speed."),
            _i("example", "Dropping from 5 m: m g h becomes ½ m v², giving v = √(2 × 9.8 × 5) ≈ 9.9 m/s."),
            _i("pitfall", "Applying conservation while friction is present — then energy leaves the mechanical account."),
            _i("use", "the problem asks about speeds or heights and you do not care about time or directions."),
            _i("check", "Which condition makes mechanical energy conserved?"),
            _i("check", "In the drop example, what cancels out of the equation?"),
            _i("check", "Where does the energy go when a slider stops, and does that break conservation?"),
        ),
    ),
    "momentum-collisions": TopicPack(
        topic_id="momentum-collisions",
        sources=(
            _s("OpenStax College Physics 2e, Ch. 8 — Linear Momentum and Collisions",
               "OpenStax (Rice University)", "open-textbook",
               "https://openstax.org/details/books/college-physics-2e",
               "Peer-reviewed textbook; momentum, impulse and elastic/inelastic collisions in one place."),
            _src(HYPER, why="Collision diagrams with the before/after momentum bookkeeping."),
            _src(KHAN, why="Momentum and impulse videos with worked collision problems.", path="science/physics"),
        ),
        items=(
            _i("fact", "Total momentum is conserved in a collision when external forces are negligible, because the internal forces pair up."),
            _i("fact", "Impulse (force × time) equals the change in momentum, which is why a longer stopping time means a smaller force."),
            _i("fact", "Elastic collisions conserve kinetic energy as well; inelastic ones do not — the missing energy becomes heat or deformation."),
            _i("analogy", "Walking off a skateboard onto a wall leaves you moving, while pushing off leaves you and the board moving in opposite directions."),
            _i("example", "A 2 kg ball at 3 m/s hitting a stationary 1 kg ball elasticly leaves at 1 m/s while the second leaves at 4 m/s."),
            _i("pitfall", "Treating air-bag and crumple-zone problems as if the impulse changed — only the stopping time and force do."),
            _i("use", "crashes, collisions, explosions, recoil — anything where objects interact briefly and strongly."),
            _i("check", "What must be small for momentum to be conserved?"),
            _i("check", "How much momentum does a 1000 kg car at 10 m/s have, and what does that mean for stopping it?"),
            _i("check", "Why can a collision conserve momentum but not kinetic energy?"),
        ),
    ),
    # ------------------------------------------------------------------- biology
    "cell-structure": TopicPack(
        topic_id="cell-structure",
        sources=(
            _s("OpenStax Biology 2e, Ch. 4 — Cell Structure",
               "OpenStax (Rice University)", "open-textbook",
               "https://openstax.org/details/books/biology-2e",
               "Peer-reviewed biology textbook used in university courses; organelle functions are tabulated."),
            _src(SCITABLE, why="Nature's teaching section; clear cell-biology summaries written by researchers."),
            _src(KHAN, why="Cell structure with diagrams and quizzes.", path="science/biology"),
        ),
        items=(
            _i("fact", "Every cell has a membrane, cytoplasm, ribosomes and genetic material — that is what makes it a cell.",
               "كل خلية لها غشاء، وسيتوبلازم، وريبوسومات، ومادة وراثية؛ وهذا ما يجعلها خلية."),
            _i("fact", "Eukaryotic cells keep their DNA in a nucleus and separate specialised jobs into organelles.",
               "الخلايا الحقيقية تحفظ DNA داخل النواة، وتوزّع الوظائف على عضيات متخصصة."),
            _i("fact", "Compartmentalisation lets hostile chemistry happen safely: digestive enzymes stay inside lysosomes, not in the cytoplasm.",
               "التقسيم إلى حجرات يسمح بتفاعلات متعارضة أن تحدث بأمان: إنزيمات الهضم تبقى داخل الليسوسوم."),
            _i("analogy", "A city: the nucleus is the library, mitochondria are power plants, the membrane is the city wall with gates.",
               "تخيّل مدينة: النواة هي المكتبة، والميتوكوندريا محطات طاقة، والغشاء سور المدينة وبواباته."),
            _i("example", "A muscle cell is packed with mitochondria because it burns a lot of energy, while a red blood cell has none and carries oxygen instead.",
               "الخلية العضلية مليئة بالميتوكوندريا لأنها تستهلك طاقة كثيرة، بينما خلية الدم الحمراء لا تحملها وتنقل الأكسجين."),
            _i("pitfall", "Saying prokaryotes have 'no structure' — they have ribosomes and a membrane, just no nucleus.",
               "لا تقل إن البدائيات «بلا تركيب»؛ فلها ريبوسومات وغشاء، لكن لا نواة."),
            _i("use", "you are reasoning about how a cell does something — first ask which organelle does that job.",
               "حين تسأل كيف تقوم الخلية بشيء، اسأل أولًا: أي عضية تقوم بهذه الوظيفة؟"),
            _i("check", "Which parts does every cell have, whatever its type?",
               "ما الأجزاء التي توجد في كل خلية مهما كان نوعها؟"),
            _i("check", "Why does a muscle cell need so many mitochondria?",
               "لماذا تحتاج الخلية العضلية ميتوكوندريا كثيرة؟"),
            _i("check", "Why is compartmentalisation important for digestion inside a cell?",
               "لماذا يهم التقسيم إلى حجرات في الهضم داخل الخلية؟"),
        ),
    ),
    "mitosis": TopicPack(
        topic_id="mitosis",
        sources=(
            _s("OpenStax Biology 2e, Ch. 10 — Cell Reproduction",
               "OpenStax (Rice University)", "open-textbook",
               "https://openstax.org/details/books/biology-2e",
               "Peer-reviewed textbook; the phases, the checkpoints and the outcomes are stated together."),
            _src(SCITABLE, why="Nature's mitosis pages pair each phase with what the chromosomes are doing."),
            _src(NCBI, why="Bookshelf cell-biology chapters cover the spindle and checkpoint machinery."),
        ),
        items=(
            _i("fact", "Mitosis turns one cell into two cells with the same genetic information.",
               "الانقسام المتساوي يحوّل خلية واحدة إلى خليتين تحملان المعلومة الوراثية نفسها."),
            _i("fact", "The phases run prophase, metaphase, anaphase, telophase — chromosomes condense, line up, separate, then two nuclei form.",
               "المراحل: الطور التمهيدي، ثم الاستوائي، ثم الانفصالي، ثم النهائي — تتكثّف الصبغيات، ثم تصطفّ، ثم تنفصل، ثم تتكوّن نواتان."),
            _i("fact", "The DNA is copied earlier, in S phase, so each chromosome already has two identical sister chromatids before mitosis starts.",
               "يُنسخ الحمض النووي قبل ذلك في طور التخليق، فيحمل كل صبغي قبل البدء نسختين متطابقتين."),
            _i("analogy", "Photocopy the document first, then split the pile: the copy happens before the separation.",
               "تخيّل أنك تصوّر المستند أولًا ثم تفرّق النسخ: النسخ يسبق الانفصال."),
            _i("example", "A cell with four chromosomes makes two cells that each have four chromosomes — same number, not half.",
               "خلية فيها أربعة صبغيات تُنتج خليتين في كل واحدة أربعة صبغيات — العدد نفسه لا نصفه."),
            _i("pitfall", "Confusing mitosis with meiosis: meiosis halves the chromosome number for gametes, mitosis keeps it.",
               "الخلط بين الانقسام المتساوي والانقسام المنصف: المنصف ينصّف عدد الصبغيات لتكوين الأمشاج، والمتساوي يحفظه."),
            _i("use", "you are explaining growth, healing and how identical cells are maintained.",
               "تشرح النمو أو التئام الجروح أو كيف تُحفظ خلايا متطابقة."),
            _i("check", "How many cells come out of one mitosis, and how many chromosomes each?",
               "كم خلية تنتج عن الانقسام المتساوي، وكم صبغيًا في كل خلية؟"),
            _i("check", "In which phase do the chromosomes line up in the middle?",
               "في أي طور تصطفّ الصبغيات في المنتصف؟"),
            _i("check", "Why do checkpoints matter for the accuracy of the whole process?",
               "لماذا تهمّ نقاط الفحص لدقة العملية كلها؟"),
        ),
    ),
    "dna-rna": TopicPack(
        topic_id="dna-rna",
        sources=(
            _s("OpenStax Biology 2e, Ch. 14 — DNA Structure and Function",
               "OpenStax (Rice University)", "open-textbook",
               "https://openstax.org/details/books/biology-2e",
               "Peer-reviewed textbook; base pairing, transcription and translation in the order they are taught."),
            _src(SCITABLE, why="Nature's DNA and gene-expression primers."),
            _src(NCBI, why="Bookshelf chapters on the genetic code and translation machinery."),
        ),
        items=(
            _i("fact", "DNA is a double helix whose strands pair A with T and G with C, which is what lets it be copied accurately.",
               "DNA سلم مزدوج تتزاوج قواعده A مع T وG مع C، ولهذا يمكن نسخه بدقة."),
            _i("fact", "Transcription copies one gene into messenger RNA in the nucleus; translation reads it into protein at the ribosome.",
               "النسخ يصنع نسخة RNA رسول من جين واحد داخل النواة، والترجمة تقرأها إلى بروتين عند الريبوسوم."),
            _i("fact", "Three bases (a codon) name one amino acid, so the reading frame decides the whole protein.",
               "كل ثلاث قواعد (كودون) تسمّي حمضًا أمينيًا واحدًا، لذلك إطار القراءة يحدد البروتين كله."),
            _i("analogy", "DNA is the master blueprint kept in the office; mRNA is the working copy carried to the workshop.",
               "DNA هو المخطط الأصلي المحفوظ في المكتب، وmRNA نسخة العمل التي تُحمل إلى الورشة."),
            _i("example", "The DNA triplet TAC is transcribed to AUG on mRNA, which the ribosome reads as the start signal.",
               "الثلاثية TAC في DNA تُنسخ إلى AUG في mRNA، ويقرأها الريبوسوم إشارةَ بدء."),
            _i("pitfall", "Mixing U and T: RNA uses uracil where DNA uses thymine.",
               "لا تخلط U وT: فالـRNA يستخدم اليوراسيل حيث يستخدم DNA الثايمين."),
            _i("use", "you are explaining inheritance, mutations or how a gene becomes a trait.",
               "تستخدم هذا حين تشرح الوراثة والطفرات وكيف يصبح الجين صفة."),
            _i("check", "Which base pairs with A, in DNA and in RNA?",
               "أي قاعدة تتزاوج مع A في DNA وفي RNA؟"),
            _i("check", "Where does transcription happen, and where does translation happen?",
               "أين يحدث النسخ، وأين تحدث الترجمة؟"),
            _i("check", "Why does deleting one base change every amino acid after it?",
               "لماذا يغيّر حذف قاعدة واحدة كل الأحماض الأمينية بعدها؟"),
        ),
    ),
    "photosynthesis": TopicPack(
        topic_id="photosynthesis",
        sources=(
            _s("OpenStax Biology 2e, Ch. 8 — Photosynthesis",
               "OpenStax (Rice University)", "open-textbook",
               "https://openstax.org/details/books/biology-2e",
               "Peer-reviewed textbook; the light reactions and the Calvin cycle are separated explicitly."),
            _src(SCITABLE, why="Nature's photosynthesis topic pages, written for teaching."),
            _src(KHAN, why="Stoichiometry and the two stages with worked examples.", path="science/biology"),
        ),
        items=(
            _i("fact", "The light reactions in the thylakoid membranes split water, release oxygen, and make ATP and NADPH.",
               "التفاعلات الضوئية في أغشية الثايلاكويد تشطر الماء، وتطلق الأكسجين، وتصنع ATP وNADPH."),
            _i("fact", "The Calvin cycle in the stroma uses that ATP and NADPH to fix carbon dioxide into sugar.",
               "دورة كالفن في السدى تستخدم ATP وNADPH لتثبيت ثاني أكسيد الكربون في سكر."),
            _i("fact", "Overall, six carbon dioxide and six water molecules give one glucose and six oxygen molecules using light energy.",
               "بالمجموع: ست جزيئات من CO2 وست من الماء تعطي جلوكوزًا واحدًا وستة أكسجين باستخدام الضوء."),
            _i("analogy", "Solar panels charging a battery (ATP), while a factory uses that power to build sugar from the air.",
               "ألواح شمسية تشحن بطارية (ATP)، بينما مصنع يستخدم هذه الطاقة ليبني السكر من الهواء."),
            _i("example", "A plant in bright light makes oxygen you can collect; in the dark the light reactions stop and oxygen production stops with them.",
               "نبتة في ضوء ساطع تُنتج أكسجينًا يمكن جمعه؛ وفي الظلام تتوقف التفاعلات الضوئية ويتوقف معها إنتاج الأكسجين."),
            _i("pitfall", "Believing plants get their mass from the soil — most of it comes from carbon dioxide in the air.",
               "لا تعتقد أن النبات يأخذ كتلته من التربة؛ معظمها من ثاني أكسيد الكربون في الهواء."),
            _i("use", "you are linking energy flow in ecosystems, or why plants release oxygen.",
               "تستخدم هذا لربط سريان الطاقة في الأنظمة البيئية، أو لماذا تطلق النباتات الأكسجين."),
            _i("check", "Which stage needs light directly, and which one does not?",
               "أي مرحلة تحتاج الضوء مباشرة، وأيهما لا تحتاجه؟"),
            _i("check", "What happens to oxygen production if you block the light reactions?",
               "ماذا يحدث لإنتاج الأكسجين إذا أوقفت التفاعلات الضوئية؟"),
            _i("check", "Where does the carbon in a plant's body come from?",
               "من أين يأتي الكربون في جسم النبات؟"),
        ),
    ),
    # --------------------------------------------------------------- programming
    "variables-types": TopicPack(
        topic_id="variables-types",
        sources=(
            _src(PYDOCS, why="The official Python tutorial introduces names, values and types in this order.",
                 path="3/tutorial/introduction.html"),
            _src(PYSTD, why="The authoritative list of built-in types and the operations they allow.",
                 path="3/library/stdtypes.html"),
            _src(MDN, why="Type behaviour explained across languages, with runnable examples.",
                 path="en-US/docs/Learn_web_development/Core/Scripting/Variables"),
        ),
        items=(
            _i("fact", "A variable is a name bound to a value; in Python the value has the type, the name does not."),
            _i("fact", "int, float, str and bool behave differently: 3 + 2 is 5, '3' + '2' is '32'."),
            _i("fact", "type(x) reports the type, and mixing types in one operation raises TypeError rather than guessing."),
            _i("analogy", "Labelled boxes: the label can be moved to a different box, and the box decides what fits inside."),
            _i("example", "count = 3, then count = count + 1 makes 4; count = 'three' is allowed but count + 1 then fails."),
            _i("pitfall", "Comparing a number with a string: 3 == '3' is False, and it silently breaks conditions."),
            _i("use", "always — the type decides which operations are legal and why an error message says what it says."),
            _i("check", "What is the type of the value in total = 12.5?"),
            _i("check", "What does 3 + 2 give, and what does '3' + '2' give?"),
            _i("check", "Why is a dynamically typed language still not type-free?"),
        ),
    ),
    "control-flow": TopicPack(
        topic_id="control-flow",
        sources=(
            _src(PYDOCS, why="The official tutorial's chapters on if/else, for and while, including Python's indentation rule.",
                 path="3/tutorial/controlflow.html"),
            _src(ATBS, why="A free, practical beginner book where control flow is used immediately in small scripts."),
            _src(MDN, why="Conditionals and loops contrasted across languages with examples.",
                 path="en-US/docs/Learn_web_development/Core/Scripting/Conditional_statements"),
        ),
        items=(
            _i("fact", "if / elif / else chooses one branch, and only the first true condition runs."),
            _i("fact", "for iterates over the items of a sequence, while repeats as long as a condition stays true."),
            _i("fact", "In Python the indentation defines the block, so a misindented line silently changes the logic."),
            _i("analogy", "A recipe: 'repeat until the sauce thickens' is a loop, 'if the oven is hot, bake' is a branch."),
            _i("example", "for n in range(5) prints 0 to 4; while count < 5 does the same but you must change count yourself."),
            _i("pitfall", "Forgetting to update the variable a while loop tests — the loop never ends."),
            _i("use", "any task that repeats or that depends on a decision."),
            _i("check", "Which branch runs when several conditions are true?"),
            _i("check", "What happens if nothing inside a while loop changes its condition?"),
            _i("check", "Why does Python use indentation instead of braces?"),
        ),
    ),
    "functions": TopicPack(
        topic_id="functions",
        sources=(
            _src(PYDOCS, why="Defining and calling functions, arguments and return values, straight from the official tutorial.",
                 path="3/tutorial/controlflow.html#defining-functions"),
            _src(PYSTD, why="The reference semantics of arguments and return values.",
                 path="3/reference/compound_stmts.html#function-definitions"),
            _src(MDN, why="Functions explained conceptually with parameters, scope and returns.",
                 path="en-US/docs/Learn_web_development/Core/Scripting/Functions"),
        ),
        items=(
            _i("fact", "A function is a named block that takes inputs, does one job, and returns a result."),
            _i("fact", "Arguments are passed by object reference, so mutating a list argument is visible to the caller."),
            _i("fact", "Variables created inside a function stay local, and a function without a return gives you None."),
            _i("analogy", "A coffee machine: beans and water in, one cup out — and the same settings give the same drink."),
            _i("example", "def area(w, h): return w * h, then area(3, 4) is 12 and can be used anywhere a number is expected."),
            _i("pitfall", "Printing instead of returning: the printed text cannot be used by the next line of code."),
            _i("use", "as soon as the same three lines appear twice — name the idea once and call it."),
            _i("check", "What does a function return if it has no return statement?"),
            _i("check", "What is the difference between a parameter and an argument?"),
            _i("check", "Why can a function change a list you passed it, but not an integer?"),
        ),
    ),
    "lists-dicts": TopicPack(
        topic_id="lists-dicts",
        sources=(
            _src(PYDOCS, why="The official chapter on data structures covers lists and dictionaries in this order.",
                 path="3/tutorial/datastructures.html"),
            _src(PYSTD, why="The exact semantics of list and dict methods, including slicing and hashing of keys.",
                 path="3/library/stdtypes.html"),
            _src(MDN, why="Arrays and objects explained for readers coming from JavaScript.",
                 path="en-US/docs/Learn_web_development/Core/Scripting/Arrays"),
        ),
        items=(
            _i("fact", "A list is an ordered sequence indexed from zero, and it is mutable."),
            _i("fact", "A dictionary maps keys to values and looks up by key in about constant time on average."),
            _i("fact", "Dict keys must be hashable (strings, numbers, tuples), so a list cannot be a key — and slicing a list copies it."),
            _i("analogy", "A numbered shelf of boxes (list) versus a phone book you open by name (dictionary)."),
            _i("example", "marks[0] is the first element; marks[-1] is the last; student['name'] looks up by key instead of position."),
            _i("pitfall", "Assuming a copy when you slice or pass a list around — the original changes and the bug looks impossible."),
            _i("use", "order matters → list; you want to look things up by name → dictionary."),
            _i("check", "What index does the first element of a list have?"),
            _i("check", "How would you store 30 students and look one up by name?"),
            _i("check", "Why can't a list be used as a dictionary key?"),
        ),
    ),
    "debugging": TopicPack(
        topic_id="debugging",
        sources=(
            _src(PYDOCS, why="The official chapter on errors and exceptions: reading tracebacks and handling failures.",
                 path="3/tutorial/errors.html"),
            _src(MDN, why="A practical method for locating errors in real code.",
                 path="en-US/docs/Learn_web_development/Core/Scripting/Debugging_JavaScript"),
            _s("pdb — The Python Debugger", "Python Software Foundation", "official-docs",
               "https://docs.python.org/3/library/pdb.html",
               "Breakpoints and inspection in the standard library — the tool this lesson tells you to reach for."),
        ),
        items=(
            _i("fact", "Read a traceback from the bottom up: the last line names the error, and the line above shows where it was raised."),
            _i("fact", "The exception type tells you the class of problem — TypeError means wrong kind of value, IndexError means wrong position."),
            _i("fact", "Fix a bug by reproducing it in the smallest example, inspecting the values, changing one thing, then re-running."),
            _i("analogy", "A car dashboard: the warning light names the system, and the last gauge before it tells you which part failed."),
            _i("example", "IndexError: list index out of range on numbers[5] when the list has only three items — the position, not the list, is wrong."),
            _i("pitfall", "Changing several lines at once: if it suddenly works you have learned nothing about the bug."),
            _i("use", "every time the program does something you did not expect — including when it runs \"fine\" but wrong."),
            _i("check", "Which line of a traceback tells you what went wrong?"),
            _i("check", "What does IndexError usually mean in plain words?"),
            _i("check", "Why is a two-line reproduction worth the effort before changing code?"),
        ),
    ),
}

#: Which catalogue topics the Arabic wording above covers (the Arabic demo is spoken,
#: not translated on the fly; other topics fall back to the English wording).
ARABIC_READY: tuple[str, ...] = tuple(
    sorted(pack.topic_id for pack in TOPIC_SOURCES.values() if any(i.ar for i in pack.items))
)


def pack_for(topic_id: str | None) -> TopicPack | None:
    if not topic_id:
        return None
    return TOPIC_SOURCES.get(topic_id)


def sources_for(topic_id: str | None) -> tuple[Source, ...]:
    pack = pack_for(topic_id)
    return pack.sources if pack else ()


def all_sources() -> dict[str, tuple[Source, ...]]:
    return {topic_id: pack.sources for topic_id, pack in TOPIC_SOURCES.items()}
