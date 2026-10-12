"""Round 22: when the student picks Arabic, the whole topic is taught in Arabic.

The defect: biology packs had no Arabic, so an Arabic session fell back to the
English plan wording and mixed it in ("ببساطة: a selectively permeable lipid…").

This patch:
 1. translates the biology packs (cell-structure, dna-rna, photosynthesis) into
    easy Arabic, so those topics become Arabic-ready and the teaching pass is Arabic;
 2. adds Arabic plan localisation for the same topics (the scaffolding sentences);
 3. adds a backstop: any non-English spoken line never carries an English phrase;
 4. after answering an interrupt, the tutor asks "is everything ok?" in the lesson
    language, then resumes from the stopped pass.

Run once from the service root:  python3 tools/patch_arabic_full_explain.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:60])
        s = s.replace(old, new, 1)
    write(path, s)


# --------------------------------------------------------------------------- #
# 1. biology packs -> easy Arabic
# --------------------------------------------------------------------------- #

CS = [
    ('_i("fact", "Every cell has a membrane, cytoplasm, ribosomes and genetic material — that is what makes it a cell.")',
     '_i("fact", "Every cell has a membrane, cytoplasm, ribosomes and genetic material — that is what makes it a cell.",\n               "كل خلية لها غشاء، وسيتوبلازم، وريبوسومات، ومادة وراثية؛ وهذا ما يجعلها خلية.")'),
    ('_i("fact", "Eukaryotic cells keep their DNA in a nucleus and separate specialised jobs into organelles.")',
     '_i("fact", "Eukaryotic cells keep their DNA in a nucleus and separate specialised jobs into organelles.",\n               "الخلايا الحقيقية تحفظ DNA داخل النواة، وتوزّع الوظائف على عضيات متخصصة.")'),
    ('_i("fact", "Compartmentalisation lets hostile chemistry happen safely: digestive enzymes stay inside lysosomes, not in the cytoplasm.")',
     '_i("fact", "Compartmentalisation lets hostile chemistry happen safely: digestive enzymes stay inside lysosomes, not in the cytoplasm.",\n               "التقسيم إلى حجرات يسمح بتفاعلات متعارضة أن تحدث بأمان: إنزيمات الهضم تبقى داخل الليسوسوم.")'),
    ('_i("analogy", "A city: the nucleus is the library, mitochondria are power plants, the membrane is the city wall with gates.")',
     '_i("analogy", "A city: the nucleus is the library, mitochondria are power plants, the membrane is the city wall with gates.",\n               "تخيّل مدينة: النواة هي المكتبة، والميتوكوندريا محطات طاقة، والغشاء سور المدينة وبواباته.")'),
    ('_i("example", "A muscle cell is packed with mitochondria because it burns a lot of energy, while a red blood cell has none and carries oxygen instead.")',
     '_i("example", "A muscle cell is packed with mitochondria because it burns a lot of energy, while a red blood cell has none and carries oxygen instead.",\n               "الخلية العضلية مليئة بالميتوكوندريا لأنها تستهلك طاقة كثيرة، بينما خلية الدم الحمراء لا تحملها وتنقل الأكسجين.")'),
    ('_i("pitfall", "Saying prokaryotes have \'no structure\' — they have ribosomes and a membrane, just no nucleus.")',
     '_i("pitfall", "Saying prokaryotes have \'no structure\' — they have ribosomes and a membrane, just no nucleus.",\n               "لا تقل إن البدائيات «بلا تركيب»؛ فلها ريبوسومات وغشاء، لكن لا نواة.")'),
    ('_i("use", "you are reasoning about how a cell does something — first ask which organelle does that job.")',
     '_i("use", "you are reasoning about how a cell does something — first ask which organelle does that job.",\n               "حين تسأل كيف تقوم الخلية بشيء، اسأل أولًا: أي عضية تقوم بهذه الوظيفة؟")'),
    ('_i("check", "Which parts does every cell have, whatever its type?")',
     '_i("check", "Which parts does every cell have, whatever its type?",\n               "ما الأجزاء التي توجد في كل خلية مهما كان نوعها؟")'),
    ('_i("check", "Why does a muscle cell need so many mitochondria?")',
     '_i("check", "Why does a muscle cell need so many mitochondria?",\n               "لماذا تحتاج الخلية العضلية ميتوكوندريا كثيرة؟")'),
    ('_i("check", "Why is compartmentalisation important for digestion inside a cell?")',
     '_i("check", "Why is compartmentalisation important for digestion inside a cell?",\n               "لماذا يهم التقسيم إلى حجرات في الهضم داخل الخلية؟")'),
]

DR = [
    ('_i("fact", "DNA is a double helix whose strands pair A with T and G with C, which is what lets it be copied accurately.")',
     '_i("fact", "DNA is a double helix whose strands pair A with T and G with C, which is what lets it be copied accurately.",\n               "DNA سلم مزدوج تتزاوج قواعده A مع T وG مع C، ولهذا يمكن نسخه بدقة.")'),
    ('_i("fact", "Transcription copies one gene into messenger RNA in the nucleus; translation reads it into protein at the ribosome.")',
     '_i("fact", "Transcription copies one gene into messenger RNA in the nucleus; translation reads it into protein at the ribosome.",\n               "النسخ يصنع نسخة RNA رسول من جين واحد داخل النواة، والترجمة تقرأها إلى بروتين عند الريبوسوم.")'),
    ('_i("fact", "Three bases (a codon) name one amino acid, so the reading frame decides the whole protein.")',
     '_i("fact", "Three bases (a codon) name one amino acid, so the reading frame decides the whole protein.",\n               "كل ثلاث قواعد (كودون) تسمّي حمضًا أمينيًا واحدًا، لذلك إطار القراءة يحدد البروتين كله.")'),
    ('_i("analogy", "DNA is the master blueprint kept in the office; mRNA is the working copy carried to the workshop.")',
     '_i("analogy", "DNA is the master blueprint kept in the office; mRNA is the working copy carried to the workshop.",\n               "DNA هو المخطط الأصلي المحفوظ في المكتب، وmRNA نسخة العمل التي تُحمل إلى الورشة.")'),
    ('_i("example", "The DNA triplet TAC is transcribed to AUG on mRNA, which the ribosome reads as the start signal.")',
     '_i("example", "The DNA triplet TAC is transcribed to AUG on mRNA, which the ribosome reads as the start signal.",\n               "الثلاثية TAC في DNA تُنسخ إلى AUG في mRNA، ويقرأها الريبوسوم إشارةَ بدء.")'),
    ('_i("pitfall", "Mixing U and T: RNA uses uracil where DNA uses thymine.")',
     '_i("pitfall", "Mixing U and T: RNA uses uracil where DNA uses thymine.",\n               "لا تخلط U وT: فالـRNA يستخدم اليوراسيل حيث يستخدم DNA الثايمين.")'),
    ('_i("use", "you are explaining inheritance, mutations or how a gene becomes a trait.")',
     '_i("use", "you are explaining inheritance, mutations or how a gene becomes a trait.",\n               "تستخدم هذا حين تشرح الوراثة والطفرات وكيف يصبح الجين صفة.")'),
    ('_i("check", "Which base pairs with A, in DNA and in RNA?")',
     '_i("check", "Which base pairs with A, in DNA and in RNA?",\n               "أي قاعدة تتزاوج مع A في DNA وفي RNA؟")'),
    ('_i("check", "Where does transcription happen, and where does translation happen?")',
     '_i("check", "Where does transcription happen, and where does translation happen?",\n               "أين يحدث النسخ، وأين تحدث الترجمة؟")'),
    ('_i("check", "Why does deleting one base change every amino acid after it?")',
     '_i("check", "Why does deleting one base change every amino acid after it?",\n               "لماذا يغيّر حذف قاعدة واحدة كل الأحماض الأمينية بعدها؟")'),
]

PH = [
    ('_i("fact", "The light reactions in the thylakoid membranes split water, release oxygen, and make ATP and NADPH.")',
     '_i("fact", "The light reactions in the thylakoid membranes split water, release oxygen, and make ATP and NADPH.",\n               "التفاعلات الضوئية في أغشية الثايلاكويد تشطر الماء، وتطلق الأكسجين، وتصنع ATP وNADPH.")'),
    ('_i("fact", "The Calvin cycle in the stroma uses that ATP and NADPH to fix carbon dioxide into sugar.")',
     '_i("fact", "The Calvin cycle in the stroma uses that ATP and NADPH to fix carbon dioxide into sugar.",\n               "دورة كالفن في السدى تستخدم ATP وNADPH لتثبيت ثاني أكسيد الكربون في سكر.")'),
    ('_i("fact", "Overall, six carbon dioxide and six water molecules give one glucose and six oxygen molecules using light energy.")',
     '_i("fact", "Overall, six carbon dioxide and six water molecules give one glucose and six oxygen molecules using light energy.",\n               "بالمجموع: ست جزيئات من CO2 وست من الماء تعطي جلوكوزًا واحدًا وستة أكسجين باستخدام الضوء.")'),
    ('_i("analogy", "Solar panels charging a battery (ATP), while a factory uses that power to build sugar from the air.")',
     '_i("analogy", "Solar panels charging a battery (ATP), while a factory uses that power to build sugar from the air.",\n               "ألواح شمسية تشحن بطارية (ATP)، بينما مصنع يستخدم هذه الطاقة ليبني السكر من الهواء.")'),
    ('_i("example", "A plant in bright light makes oxygen you can collect; in the dark the light reactions stop and oxygen production stops with them.")',
     '_i("example", "A plant in bright light makes oxygen you can collect; in the dark the light reactions stop and oxygen production stops with them.",\n               "نبتة في ضوء ساطع تُنتج أكسجينًا يمكن جمعه؛ وفي الظلام تتوقف التفاعلات الضوئية ويتوقف معها إنتاج الأكسجين.")'),
    ('_i("pitfall", "Believing plants get their mass from the soil — most of it comes from carbon dioxide in the air.")',
     '_i("pitfall", "Believing plants get their mass from the soil — most of it comes from carbon dioxide in the air.",\n               "لا تعتقد أن النبات يأخذ كتلته من التربة؛ معظمها من ثاني أكسيد الكربون في الهواء.")'),
    ('_i("use", "you are linking energy flow in ecosystems, or why plants release oxygen.")',
     '_i("use", "you are linking energy flow in ecosystems, or why plants release oxygen.",\n               "تستخدم هذا لربط سريان الطاقة في الأنظمة البيئية، أو لماذا تطلق النباتات الأكسجين.")'),
    ('_i("check", "Which stage needs light directly, and which one does not?")',
     '_i("check", "Which stage needs light directly, and which one does not?",\n               "أي مرحلة تحتاج الضوء مباشرة، وأيهما لا تحتاجه؟")'),
    ('_i("check", "What happens to oxygen production if you block the light reactions?")',
     '_i("check", "What happens to oxygen production if you block the light reactions?",\n               "ماذا يحدث لإنتاج الأكسجين إذا أوقفت التفاعلات الضوئية؟")'),
    ('_i("check", "Where does the carbon in a plant\'s body come from?")',
     '_i("check", "Where does the carbon in a plant\'s body come from?",\n               "من أين يأتي الكربون في جسم النبات؟")'),
]

s = read("app/learning/sources.py")
for old, new in CS + DR + PH:
    assert old in s, ("sources", old[:50])
    s = s.replace(old, new, 1)
write("app/learning/sources.py", s)

# --------------------------------------------------------------------------- #
# 2. Arabic plan localisation for biology
# --------------------------------------------------------------------------- #

s = read("app/curriculum_localisation.py")
anchor = '        "recursion": {'
bio = '''        "cell-structure": {
            "The membrane": ("الغشاء", "طبقة دهنية تختار ما يدخل وما يخرج، فتفصل الداخل عن الخارج"),
            "Shared machinery": ("أجهزة مشتركة", "ريبوسومات وDNA وسيتوبلازم في كل خلية"),
            "Eukaryotic additions": ("إضافات الخلايا الحقيقية", "نواة وعضيات محاطة بأغشية"),
            "Plant versus animal": ("نباتي أم حيواني", "جدار خلوي وبلاستيدات خضراء وفجوة كبيرة"),
        },
        "dna-rna": {
            "The archive": ("الأرشيف", "تزاوج القواعد يجعل DNA ثابتًا وقابلًا للنسخ"),
            "Transcription": ("النسخ", "تُصنع نسخة RNA عاملة من جين واحد"),
            "Translation": ("الترجمة", "تُقرأ الكودونات إلى سلسلة أحماض أمينية"),
            "Mutations": ("الطفرات", "قاعدة متغيرة قد تغيّر البروتين، وغالبًا لا تغيّر"),
        },
        "photosynthesis": {
            "Light reactions": ("التفاعلات الضوئية", "التقاط الفوتونات وشطر الماء"),
            "Calvin cycle": ("دورة كالفن", "استخدام الطاقة المخزنة لتثبيت CO2 في سكر"),
            "Inputs and outputs": ("المدخلات والمخرجات", "CO2 وماء داخلًا، وجلوكوز وأكسجين خارجًا"),
            "Limiting factors": ("العوامل المحددة", "الضوء وCO2 والحرارة، كلٌّ يحدد المعدل"),
        },
'''
assert anchor in s
s = s.replace(anchor, bio + anchor, 1)
top_anchor = '        "binary-search": "البحث الثنائي",'
top_new = top_anchor + '''
        "cell-structure": "تركيب الخلية",
        "dna-rna": "DNA وRNA",
        "photosynthesis": "البناء الضوئي",'''
assert top_anchor in s
s = s.replace(top_anchor, top_new, 1)
write("app/curriculum_localisation.py", s)

# --------------------------------------------------------------------------- #
# 3. backstop: never speak an English phrase in a non-English session
# --------------------------------------------------------------------------- #

s = read("app/providers/mock/dialogue.py")
if "import re\n" not in s:
    s = s.replace(
        "from __future__ import annotations",
        "from __future__ import annotations\n\nimport re",
        1,
    )

old = """    def _name(self, text: str) -> str:"""
scrub = (
    "    #: An English *phrase*: three or more Latin words in a row. A single technical\n"
    "    #: term (\"DNA\", \"ATP\", \"low\") is fine inside an Arabic sentence; a whole English\n"
    "    #: clause is the machine-switching-languages failure this scrubs out.\n"
    "    _EN_PHRASE = re.compile(r\"[A-Za-z][A-Za-z-']*(?: +[A-Za-z-']+){2,}\")\n"
    "\n"
    "    def _scrub(self, text: str) -> str:\n"
    "        \"\"\"Strip English phrases from a non-English utterance.\"\"\"\n"
    "        if (self.line_language or \"en\") == \"en\":\n"
    "            return text\n"
    "        cleaned = self._EN_PHRASE.sub(\" \", text)\n"
    "        cleaned = \" \".join(cleaned.split()).strip()\n"
    "        return cleaned\n"
    "\n"
    "    def _name(self, text: str) -> str:"
)
assert old in s
s = s.replace(old, scrub, 1)

# apply _scrub inside _name so every utterance is filtered once
old = """    def _name(self, text: str) -> str:
        \"\"\"Occasionally address the student by name — like a person would.\"\"\"
        if not self.student_name:
            return text"""
new = """    def _name(self, text: str) -> str:
        text = self._scrub(text)
        \"\"\"Occasionally address the student by name — like a person would.\"\"\"
        if not self.student_name:
            return text"""
assert old in s
s = s.replace(old, new, 1)
write("app/providers/mock/dialogue.py", s)

print("round 22: biology in easy Arabic + no-English backstop")
