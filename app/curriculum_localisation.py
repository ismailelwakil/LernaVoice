"""Speak the lesson plan in the student's language.

The course catalogue is written in English (`app/curriculum.py`); the tutoring
around it is localised. With a real voice this gap becomes audible: an Arabic
voice reading *"The idea of halving. Compare with the middle…"* in the middle of
an Arabic sentence sounds like a machine switching languages mid-breath.

This module carries curated translations for the topics the demo is actually
opened with. It is deliberately small and explicit rather than clever:

  * a language + topic with a translation → the tutor *says* the local wording;
  * anything else → the original English plan (unchanged behaviour).

Live vendor sessions do not need this: the model receives the plan plus the
instruction to express it in the target language. This is for the offline demo
(and for the first turn before the model takes over).
"""

from __future__ import annotations

#: language → topic key → {english title: (localised title, localised goal)}
LOCALISED_STEPS: dict[str, dict[str, dict[str, tuple[str, str]]]] = {
    "ar": {
        "binary-search": {
            "The idea of halving": (
                "فكرة التنصيف",
                "نقارن بالعنصر الأوسط، ونُهمل النصف الذي يستحيل أن يحتوي على الهدف",
            ),
            "Trace it on a small array": (
                "نتتبّع الخطوات على مصفوفة صغيرة",
                "16 عنصرًا، ثم 8، ثم 4، ثم 2، حتى نصل إلى العنصر",
            ),
            "Why the cost is logarithmic": (
                "لماذا التكلفة لوغاريتمية",
                "يتنصّف المجال في كل خطوة، فيكون عدد الخطوات لوغاريتم عدد العناصر",
            ),
            "Common mistakes": (
                "الأخطاء الشائعة",
                "مصفوفة غير مرتبة، وحساب نقطة المنتصف بطريقة تسبب overflow",
            ),
        },
        "cell-structure": {
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
        "recursion": {
            "The base case": (
                "الحالة الأساسية",
                "لا بد من شرط يوقف الاستدعاء، وإلا استمر البرنامج بلا نهاية",
            ),
            "The recursive case": (
                "الحالة التكرارية",
                "نحل جزءًا صغيرًا من المسألة، ونترك الباقي للدالة نفسها",
            ),
            "The stack unwinds": (
                "عودة الاستدعاءات",
                "عند الوصول إلى الحالة الأساسية تعود الاستدعاءات بالترتيب العكسي",
            ),
            "When recursion is the wrong tool": (
                "متى لا نستخدم الاستدعاء الذاتي",
                "أحيانًا تكون الحلقة العادية أوضح وأقل استهلاكًا للذاكرة",
            ),
        },
        "merge-sort": {
            "Divide": (
                "التقسيم",
                "نقسم المصفوفة إلى نصفين، ونسلّم كل نصف إلى الدالة نفسها",
            ),
            "Conquer": (
                "الترتيب",
                "عندما يصل النصف إلى عنصر واحد يكون مرتبًا",
            ),
            "The merge step": (
                "خطوة الدمج",
                "نقارن أول عنصر من كل نصف فنأخذ الأصغر، حتى تنتهي القائمتان",
            ),
            "Cost and stability": (
                "التكلفة والاستقرار",
                "التكلفة n لوغاريتم n، والترتيب مستقر لكنه يحتاج ذاكرة إضافية",
            ),
        },
    },
}


#: language → topic key → localised topic title (shown in the greeting)
LOCALISED_TOPICS: dict[str, dict[str, str]] = {
    "ar": {
        "binary-search": "البحث الثنائي",
        "cell-structure": "تركيب الخلية",
        "dna-rna": "DNA وRNA",
        "photosynthesis": "البناء الضوئي",
        "recursion": "الاستدعاء الذاتي",
        "merge-sort": "ترتيب الدمج",
    },
}


def localise_topic(language: str, topic_key: str | None, title: str) -> str:
    """The topic's name in `language`, when curated."""
    table = LOCALISED_TOPICS.get((language or "en").lower(), {})
    if topic_key and topic_key in table:
        return table[topic_key]
    return title


def localise_step(language: str, topic_key: str | None, title: str, goal: str) -> tuple[str, str]:
    """(title, goal) in `language` when a translation exists, else the input."""
    table = LOCALISED_STEPS.get((language or "en").lower(), {})
    for key, steps in table.items():
        if topic_key and key != topic_key:
            continue
        for english_title, translated in steps.items():
            if english_title.lower() == (title or "").lower():
                return translated
    return title, goal


def localise_sections(
    language: str, topic_key: str | None, sections: list[dict]
) -> list[dict]:
    """The plan the tutor speaks: localised where curated, untouched otherwise."""
    if not sections or (language or "en").lower() == "en":
        return sections
    out: list[dict] = []
    for section in sections:
        title = str(section.get("title", ""))
        goal = str(section.get("goal", ""))
        local_title, local_goal = localise_step(language, topic_key, title, goal)
        merged = dict(section)
        merged["title"] = local_title
        merged["goal"] = local_goal
        merged["original_title"] = title
        merged["localised"] = local_title != title
        out.append(merged)
    return out


def covered_topics(language: str) -> list[str]:
    return sorted(LOCALISED_STEPS.get((language or "en").lower(), {}))
