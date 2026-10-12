"""Round 20, part 1: sectioned content + level-aware selection.

Gives every teaching item a *section* (the lesson part it belongs to) and teaches
each section properly, instead of spreading five facts over four parts.

Run once from the service root:  python3 tools/patch_teacher_content.py
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
# 1. Item gains a section, and `_i()` can carry it
# --------------------------------------------------------------------------- #

sub("app/learning/sources.py", [
    (
        '''    kind: str  # fact | analogy | example | pitfall | use | check
    en: str
    ar: str = ""''',
        '''    kind: str  # fact | analogy | example | pitfall | use | check
    en: str
    ar: str = ""
    #: Which lesson part this belongs to (1-based, matching the plan's order).
    #: 0 = belongs to the topic as a whole (checks). Sectioned items let a pass
    #: teach its own part properly instead of spreading a few facts across the
    #: whole lesson — see `app/learning/lesson_script.py`.
    section: int = 0''',
    ),
    (
        '''    def as_dict(self, language: str = "en") -> dict[str, str]:
        return {"kind": self.kind, "text": self.text(language), "english": self.en}''',
        '''    def as_dict(self, language: str = "en") -> dict[str, str]:
        return {
            "kind": self.kind,
            "text": self.text(language),
            "english": self.en,
            "section": self.section,
        }''',
    ),
    (
        '''def _i(kind: str, en: str, ar: str = "") -> Item:
    return Item(kind=kind, en=en, ar=ar)''',
        '''def _i(kind: str, en: str, ar: str = "", section: int = 0) -> Item:
    return Item(kind=kind, en=en, ar=ar, section=section)''',
    ),
])

# --------------------------------------------------------------------------- #
# 2. binary search: a real, sectioned explanation in both languages
# --------------------------------------------------------------------------- #

BINARY_ITEMS = '''        items=(
            # --- 1. The idea of halving --------------------------------------
            _i("analogy", "Think of looking a word up in a dictionary: open the middle, decide which half it must be in, repeat.",
               "تخيّل أنك تبحث عن كلمة في المعجم: افتح المنتصف، ثم اختر النصف الذي يجب أن تكون فيه الكلمة، وأعد الخطوة.", 1),
            _i("fact", "Binary search is built on one idea: the data is sorted, so a single comparison with the middle tells you which half can be thrown away.",
               "البحث الثنائي مبني على فكرة واحدة: البيانات مرتبة، لذلك تكفي مقارنة واحدة بالعنصر الأوسط لتعرف أي نصف يمكن استبعاده.", 1),
            _i("fact", "It looks at the middle element of a sorted list and discards the half that cannot contain the target.",
               "ينظر إلى العنصر الأوسط في قائمة مرتبة، ثم يستبعد النصف الذي يستحيل أن يحتوي على الهدف.", 1),
            _i("fact", "Sorted order is not a detail, it is the whole assumption: comparing with the middle says nothing at all while the data is unordered.",
               "الترتيب ليس تفصيلًا، بل هو الشرط كله: مقارنة العنصر الأوسط لا تقول شيئًا على بيانات غير مرتبة.", 1),
            _i("fact", "Because every comparison removes half the candidates, the part still in play shrinks by half at every step.",
               "ولأن كل مقارنة تستبعد نصف المرشحين، فإن الجزء الذي ما زال قيد البحث ينكمش إلى النصف في كل خطوة.", 1),
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
            _i("use", "That is why sorted indexes, database key lookups and version lists all rest on binary search.",
               "ولهذا تُبنى الفهارس المرتبة والبحث بمفاتيح قواعد البيانات وقوائم الإصدارات على البحث الثنائي.", 3),
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
        ),'''

src = read("app/learning/sources.py")
start = src.index('        items=(\n            _i("fact", "Binary search looks at the middle element')
end = src.index("        ),\n    ),", start) + len("        ),")
write("app/learning/sources.py", src[:start] + BINARY_ITEMS + src[end:])

# --------------------------------------------------------------------------- #
# 3. the brief: sectioned items, chosen by level
# --------------------------------------------------------------------------- #

sub("app/learning/explainer.py", [
    (
        """    kind: str
    text: str
    english: str
    sources: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()""",
        """    kind: str
    text: str
    english: str
    sources: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()
    #: The lesson part this belongs to (1-based); 0 when the pack is unsectioned.
    section: int = 0""",
    ),
    (
        """            "sources": list(self.sources),
            "concepts": list(self.concepts),
        }""",
        """            "sources": list(self.sources),
            "concepts": list(self.concepts),
            "section": self.section,
        }""",
    ),
    (
        """def _item_move(item: Item, kind: str, sources: tuple[str, ...], language: str,
               frame_language: str, concepts: tuple[str, ...]) -> Move:""",
        """#: How many of each kind a level gets *per lesson part*. A section is taught
#: properly at every level: beginners get the picture and the plain idea, an
#: advanced student gets the reasoning, the edge cases and where it is used.
LEVEL_ITEMS: dict[str, dict[str, int]] = {
    "beginner": {"analogy": 1, "fact": 2, "example": 1, "pitfall": 1, "use": 0, "why": 0},
    "intermediate": {"analogy": 0, "fact": 3, "example": 1, "pitfall": 1, "use": 1, "why": 1},
    "advanced": {"analogy": 0, "fact": 3, "example": 1, "pitfall": 2, "use": 1, "why": 1},
}


def _select_sectioned(pack: "TopicPack", level: str) -> list[tuple[Item, str]]:
    \"\"\"The items to teach, per lesson part, in the order a teacher would say them.

    Returns `(item, move_kind)` pairs: the first fact of a part is its *idea*, the
    analogy is the *picture*, and the rest keep their own kind.
    \"\"\"
    budget = LEVEL_ITEMS.get(level, LEVEL_ITEMS["intermediate"])
    chosen: list[tuple[Item, str]] = []
    sections = sorted({i.section for i in pack.items if i.section})
    for section in sections:
        used: dict[str, int] = {}
        first_fact = True
        for item in pack.items:
            if item.section != section or item.kind == "check":
                continue
            limit = budget.get(item.kind)
            if not limit or used.get(item.kind, 0) >= limit:
                continue
            used[item.kind] = used.get(item.kind, 0) + 1
            if item.kind == "analogy":
                kind = "hook"
            elif item.kind == "fact":
                kind = "idea" if first_fact else "fact"
                first_fact = False
            else:
                kind = item.kind
            chosen.append((item, kind))
    return chosen


def _item_move(item: Item, kind: str, sources: tuple[str, ...], language: str,
               frame_language: str, concepts: tuple[str, ...], section: int = 0) -> Move:""",
    ),
    (
        """        sources=sources,
        concepts=concepts,
    )""",
        """        sources=sources,
        concepts=concepts,
        section=section or getattr(item, "section", 0),
    )""",
    ),
    (
        """    source_ids = tuple(s.id for s in pack.sources)""",
        """    source_ids = tuple(s.id for s in pack.sources)
    sectioned = any(getattr(i, "section", 0) for i in pack.items)""",
    ),
    (
        """    if style.analogy:
        add("hook", pack.first("analogy"))""",
        """    if sectioned:
        # Teach the lesson part by part: every part gets its own idea, example and
        # trap for this level (see LEVEL_ITEMS), instead of a few facts spread thin.
        for item, kind in _select_sectioned(pack, level_key):
            add(kind, item)
        check = _check_for(pack, style, language)
        if check is not None:
            lead_key = {"closed": "check", "applied": "check_applied", "open": "check_open"}[style.check]
            lead = FRAMES[frame_language].get(lead_key, FRAMES["en"][lead_key])
            moves.append(
                Move(
                    kind="check",
                    text=f"{lead} {check.text(language)}".strip(),
                    english=check.en,
                    concepts=concepts,
                )
            )
        return ExplanationBrief(
            topic_id=resolved_id,
            topic=title,
            level=level_key,
            language=language,
            style=style,
            moves=tuple(moves),
            sources=pack.sources,
            plan=tuple(steps),
            grounding="curated",
            frames=frame_language,
        )

    if style.analogy:
        add("hook", pack.first("analogy"))""",
    ),
])

print("sectioned content + level selection in place")
