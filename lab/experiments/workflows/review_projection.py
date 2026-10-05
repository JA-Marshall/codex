"""Deterministic, allowlisted reviewer content without internal routing fields."""


def validate_presentation(value):
    if not isinstance(value, dict) or set(value) - {"request", "decisions", "questions", "scope", "assumptions", "acceptance", "evidence", "candidate", "limitations"}:
        raise ValueError("invalid presentation object")
    for key, item in value.items():
        if key in ("request", "scope", "candidate"):
            if not isinstance(item, str):
                raise ValueError("presentation text required")
        elif key != "questions":
            if not isinstance(item, list) or any(not isinstance(text, str) for text in item):
                raise ValueError("presentation text list required")
        else:
            if not isinstance(item, list) or not 1 <= len(item) <= 8:
                raise ValueError("invalid question list")
            ids = set()
            for q in item:
                if not isinstance(q, dict) or set(q) != {"id", "header", "question", "options"}:
                    raise ValueError("invalid question fields")
                if any(not isinstance(q[k], str) or not q[k] for k in ("id", "header", "question")) or q["id"] in ids:
                    raise ValueError("invalid question text or repeated ID")
                ids.add(q["id"])
                if not isinstance(q["options"], list) or len(q["options"]) > 32:
                    raise ValueError("invalid options")
                for option in q["options"]:
                    if not isinstance(option, dict) or not {"label", "description"} <= set(option) or set(option) - {"id", "label", "description"} or any(not isinstance(v, str) for v in option.values()):
                        raise ValueError("invalid option fields")


def project_question(params, *, request, decisions=(), redactions=()):
    if not isinstance(params, dict) or not isinstance(params.get("questions"), list):
        raise ValueError("structured questions required")
    substitutions = sorted(redactions, key=lambda pair: -len(pair[0]))
    if any(not isinstance(a, str) or not a or not isinstance(b, str) for a, b in substitutions):
        raise ValueError("invalid deterministic redactions")

    def text(value, limit=16384):
        if not isinstance(value, str) or len(value.encode()) > limit:
            raise ValueError("invalid presentation text")
        for source, neutral in substitutions:
            value = value.replace(source, neutral)
        return value

    questions = []
    for raw in params["questions"]:
        if not isinstance(raw, dict) or not {"id", "header", "question"} <= set(raw):
            raise ValueError("invalid native question")
        question = {"id": text(raw["id"], 256), "header": text(raw["header"], 256),
                    "question": text(raw["question"]), "options": []}
        # IDs are protocol values and must remain exact, even if they contain
        # an identity clue. Record the limitation instead of changing routing.
        question["id"] = raw["id"]
        for option in raw.get("options", []):
            if not isinstance(option, dict) or not {"label", "description"} <= set(option):
                raise ValueError("invalid native option")
            value = {"label": text(option["label"]), "description": text(option["description"])}
            if "id" in option:
                value["id"] = option["id"]
            question["options"].append(value)
        questions.append(question)
    if not 1 <= len(questions) <= 8 or len({q["id"] for q in questions}) != len(questions):
        raise ValueError("invalid question batch")
    return {"request": text(request), "decisions": [text(value) for value in decisions],
            "questions": questions,
            "limitations": ["Question and option protocol IDs are preserved; structure and writing style may reveal the workflow."]}
