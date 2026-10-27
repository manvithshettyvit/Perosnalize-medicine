#!/usr/bin/env python3
"""Create a compact, browser-ready aggregate from the attached UCI review zips."""

import csv
import html
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "attached_assets"
OUTPUT = (
    ROOT
    / "artifacts"
    / "medicine-review-insights"
    / "public"
    / "data"
    / "medicine-review-summary.json"
)

SOURCES = [
    ("DATA1_1793095336159.zip", "trainingRows"),
    ("DATA2_1793095336161.zip", "testingRows"),
]

CONCERNS = {
    "side effects": ("side effect", "side effects"),
    "weight gain": ("weight gain", "gained weight"),
    "sleep": ("sleep", "insomnia", "drowsy", "sleepy"),
    "anxiety": ("anxiety", "anxious"),
    "pain": ("pain", "painful", "ache"),
    "nausea": ("nausea", "nauseous"),
    "headache": ("headache", "migraine"),
    "fatigue": ("fatigue", "tired", "exhausted"),
    "mood": ("mood", "emotional", "irritable"),
    "effectiveness": ("effective", "worked", "works", "helped", "improved"),
}

STOP_WORDS = set(
    """a about after again against all am an and any are as at be because been
    before being below between both but by can did do does doing down during each
    few for from further had has have having he her here hers herself him himself
    his how i if in into is it its itself just me more most my myself no nor not
    of off on once only or other our ours ourselves out over own same she should
    so some such than that the their theirs them themselves then there these they
    this those through to too under until up very was we were what when where which
    while who whom why will with you your yours yourself yourselves medicine drug
    medication taking take took use used using""".split()
)


def clean_review(raw):
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_condition(raw):
    condition = html.unescape(raw or "")
    if "users found this comment helpful" in condition.lower():
        return ""
    condition = re.sub(r"<[^>]+>", " ", condition)
    condition = re.sub(r"\s+", " ", condition).strip()
    if not condition or re.search(r"</?span\b|comment helpful", condition, re.I):
        return ""

    # The source archive contains a few labels cut off at the final character.
    known_truncations = {
        "not listed / othe": "Not Listed / Other",
        "bipolar disorde": "Bipolar Disorder",
    }
    return known_truncations.get(condition.casefold(), condition)


def review_words(text):
    return [
        word
        for word in re.findall(r"[a-z][a-z'-]{2,}", text.lower())
        if word not in STOP_WORDS
    ]


def parse_rows(archive_path):
    with zipfile.ZipFile(archive_path) as archive:
        csv_name = next(
            (name for name in archive.namelist() if name.lower().endswith(".csv")),
            None,
        )
        if not csv_name:
            raise ValueError(f"No CSV found in {archive_path.name}")
        with archive.open(csv_name) as data:
            text_stream = (line.decode("utf-8", errors="replace") for line in data)
            yield from csv.DictReader(text_stream)


def main():
    groups = {}
    drugs = set()
    conditions = set()
    global_terms = Counter()
    global_bigrams = Counter()
    source_totals = {"trainingRows": 0, "testingRows": 0}
    included_totals = {"trainingRows": 0, "testingRows": 0}

    for archive_name, split_key in SOURCES:
        archive_path = DATA_DIR / archive_name
        if not archive_path.exists():
            raise FileNotFoundError(f"Missing attached dataset: {archive_path}")
        for row in parse_rows(archive_path):
            source_totals[split_key] += 1
            drug = (row.get("drugName") or "").strip()
            condition = clean_condition(row.get("condition"))
            review = clean_review(row.get("review") or "")
            try:
                rating = int(row.get("rating", ""))
                useful = max(0, int(row.get("usefulCount", 0) or 0))
            except (TypeError, ValueError):
                continue
            if not drug or not condition or not review or not 1 <= rating <= 10:
                continue

            included_totals[split_key] += 1
            drugs.add(drug)
            conditions.add(condition)
            key = (condition, drug)
            group = groups.get(key)
            if group is None:
                group = {
                    "drugName": drug,
                    "condition": condition,
                    "reviewCount": 0,
                    "ratingTotal": 0,
                    "positive": 0,
                    "neutral": 0,
                    "negative": 0,
                    "usefulTotal": 0,
                    "concernCounts": Counter(),
                    "terms": Counter(),
                    "evidence": [],
                }
                groups[key] = group

            group["reviewCount"] += 1
            group["ratingTotal"] += rating
            group["usefulTotal"] += useful
            if rating >= 8:
                group["positive"] += 1
            elif rating >= 5:
                group["neutral"] += 1
            else:
                group["negative"] += 1

            lower = review.lower()
            for label, variants in CONCERNS.items():
                if any(variant in lower for variant in variants):
                    group["concernCounts"][label] += 1

            tokens = review_words(review)
            group["terms"].update(tokens)
            global_terms.update(tokens)
            global_bigrams.update(
                f"{left} {right}" for left, right in zip(tokens, tokens[1:])
            )
            candidate = {
                "text": review[:360],
                "rating": rating,
                "date": (row.get("date") or "").strip(),
                "usefulCount": useful,
            }
            # Retain only the two most useful short excerpts per group.
            group["evidence"].append(candidate)
            group["evidence"].sort(
                key=lambda item: (item["usefulCount"], item["rating"]),
                reverse=True,
            )
            del group["evidence"][2:]

    medicines = []
    for group in groups.values():
        count = group["reviewCount"]
        medicines.append(
            {
                "drugName": group["drugName"],
                "condition": group["condition"],
                "reviewCount": count,
                "averageRating": round(group["ratingTotal"] / count, 2),
                "positivePercent": round(group["positive"] * 100 / count, 1),
                "neutralPercent": round(group["neutral"] * 100 / count, 1),
                "negativePercent": round(group["negative"] * 100 / count, 1),
                "averageUseful": round(group["usefulTotal"] / count, 2),
                "concernCounts": dict(group["concernCounts"]),
                "topTerms": [
                    term for term, _ in group["terms"].most_common(8)
                ],
                "evidence": group["evidence"],
            }
        )

    medicines.sort(key=lambda item: (item["condition"].lower(), item["drugName"].lower()))
    payload = {
        "meta": {
            **source_totals,
            "processedRows": sum(included_totals.values()),
            "excludedRows": sum(source_totals.values())
            - sum(included_totals.values()),
            "totalRows": sum(included_totals.values()),
            "uniqueDrugCount": len(drugs),
            "conditionCount": len(conditions),
            "source": "UCI Drug Review Dataset (KUC Hackathon Winter 2018)",
            "sentimentMethod": "Rating proxy: 8–10 positive, 5–7 neutral, 1–4 negative.",
        },
        "languageInsights": {
            "topTerms": [
                {"term": term, "count": count}
                for term, count in global_terms.most_common(18)
            ],
            "topPhrases": [
                {"term": term, "count": count}
                for term, count in global_bigrams.most_common(12)
            ],
        },
        "medicines": medicines,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                **payload["meta"],
                "medicineConditionPairs": len(medicines),
                "outputBytes": OUTPUT.stat().st_size,
                "output": str(OUTPUT.relative_to(ROOT)),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Dataset preparation failed: {error}", file=sys.stderr)
        raise
