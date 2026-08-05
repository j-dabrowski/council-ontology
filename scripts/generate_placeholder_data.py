"""
One-off bootstrap: write structurally-valid, obviously-fake dashboard
snapshots to frontend/public/data/, so Vercel has something real to build
and serve while the draft/publish pipeline (council draft / council
publish) is still being exercised for the first time on real data.

Deliberately NOT wired into `council <cmd>` — this is not a pipeline stage,
it never reads council.db, and it should never be run as part of a normal
draft/publish cycle. Run directly:

    python scripts/generate_placeholder_data.py

Every value here is fake: invented councillor names ("Councillor Example A"
etc. — never a real name, see docs/TESTING.md), placeholder quote text,
round numbers. The shape matches every interface in frontend/src/api.ts
exactly, so `npm run build` and the deployed site behave identically to a
real publish — just with content nobody could mistake for a real finding.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "data"

GENERATED_AT = datetime.now(UTC).isoformat()

FAKE_QUOTE = "[placeholder quote — not a real minute, generated for bootstrap purposes]"

NAMES = [
    "Councillor Example A",
    "Councillor Example B",
    "Councillor Example C",
    "Councillor Example D",
]
MAYOR = "Councillor Example A"


def _write(name: str, data) -> None:
    path = OUTPUT_DIR / f"{name}.json"
    path.write_text(json.dumps({"published_at": GENERATED_AT, "data": data}, indent=2))
    print(f"  wrote {path.relative_to(OUTPUT_DIR.parent.parent.parent)}")


def build_scorecard() -> dict:
    tests = [
        {
            "test_id": "placeholder_supportive_1",
            "title": "Placeholder Test — Supportive Example",
            "genre": "Placeholder Genre",
            "principle": "Placeholder principle text describing a recognised good-governance criterion.",
            "question": "Placeholder question this test answers?",
            "valence": "supportive",
            "grade": "A",
            "headline": "Placeholder headline — sample supportive finding",
            "verdict": "PLACEHOLDER DATA — not a real finding. Sample supportive verdict text.",
            "data_ok": True,
            "n": 42,
            "base_rate": "50%",
            "era": None,
            "detail_panel": None,
            "series": [{"x": 2020, "y": 10}, {"x": 2021, "y": 14}, {"x": 2022, "y": 18}],
            "chart": {
                "kind": "bars",
                "unit": "%",
                "refline": {"label": "Placeholder baseline", "value": 50},
                "bars": [
                    {"label": "Placeholder Motion Example", "value": 62, "highlight": True},
                    {"label": "Placeholder Motion Example 2", "value": 48},
                ],
            },
        },
        {
            "test_id": "placeholder_neutral_1",
            "title": "Placeholder Test — Neutral Example",
            "genre": "Placeholder Genre",
            "principle": "Placeholder principle text.",
            "question": "Placeholder question?",
            "valence": "neutral",
            "grade": "B",
            "headline": "Placeholder headline — sample neutral finding",
            "verdict": "PLACEHOLDER DATA — not a real finding. Sample neutral verdict text.",
            "data_ok": True,
            "n": 17,
            "base_rate": None,
            "era": "post",
            "detail_panel": None,
            "series": [{"x": 2020, "y": 5}, {"x": 2021, "y": 5}, {"x": 2022, "y": 6}],
            "chart": {
                "kind": "line",
                "unit": None,
                "refline": None,
                "points": [{"x": 2020, "y": 5}, {"x": 2021, "y": 5}, {"x": 2022, "y": 6}],
            },
        },
        {
            "test_id": "placeholder_critical_1",
            "title": "Placeholder Test — Critical Example",
            "genre": "Placeholder Genre",
            "principle": "Placeholder principle text.",
            "question": "Placeholder question?",
            "valence": "critical",
            "grade": "D",
            "headline": "Placeholder headline — sample critical finding",
            "verdict": "PLACEHOLDER DATA — not a real finding. Sample critical verdict text.",
            "data_ok": True,
            "n": 8,
            "base_rate": "20%",
            "era": None,
            "detail_panel": None,
            "series": [],
            "chart": None,
        },
        {
            "test_id": "placeholder_not_computable",
            "title": "Placeholder Test — Not Computable Example",
            "genre": "Placeholder Genre",
            "principle": "Placeholder principle text.",
            "question": "Placeholder question?",
            "valence": "neutral",
            "grade": "N/A",
            "headline": "Not computable on this placeholder corpus",
            "verdict": "PLACEHOLDER DATA — sample not-computable row.",
            "data_ok": False,
            "n": None,
            "base_rate": None,
            "era": None,
            "detail_panel": None,
            "series": [],
            "chart": None,
        },
    ]
    return {
        "summary": {
            "n_tests": len(tests),
            "n_supportive": 1,
            "n_neutral": 1,
            "n_critical": 1,
            "n_not_computable": 1,
        },
        "tests": tests,
    }


def build_interests() -> list:
    return [
        {
            "councillor_id": i + 1,
            "councillor_name": name,
            "total": 5 + i,
            "by_type": {"financial": 2, "proximity": 1, "impartiality": 1},
            "top_topics": ["Placeholder Topic A", "Placeholder Topic B"],
        }
        for i, name in enumerate(NAMES)
    ]


def build_divergence() -> dict:
    return {
        "total_matched": 20,
        "diverged_count": 2,
        "followed_count": 18,
        "compliance_rate": 0.9,
        "year_min": 2020,
        "year_max": 2024,
        "exceptions": [
            {
                "meeting_date": "2022-03-01",
                "item_number": "10.1",
                "title": "Placeholder Agenda Item",
                "officer_recommendation": "Placeholder officer recommendation text.",
                "council_outcome": "CARRIED",
                "match_confidence": 0.9,
                "motion_text": "Placeholder motion text.",
                "quote": FAKE_QUOTE,
            }
        ],
    }


def build_co_movers() -> dict:
    pairs = [
        {"mover_id": 1, "mover_name": NAMES[0], "seconder_id": 2, "seconder_name": NAMES[1], "count": 12},
        {"mover_id": 2, "mover_name": NAMES[1], "seconder_id": 3, "seconder_name": NAMES[2], "count": 7},
    ]
    names = sorted({n for p in pairs for n in (p["mover_name"], p["seconder_name"])})
    return {
        "nodes": [{"id": n} for n in names],
        "links": [
            {"source": p["mover_name"], "target": p["seconder_name"], "value": p["count"]}
            for p in pairs
        ],
        "pairs": pairs,
    }


def build_alignment() -> dict:
    return {
        "pairs": [
            {
                "name_a": NAMES[0], "name_b": NAMES[1],
                "agreement_rate": 0.91, "shared_votes": 120,
                "is_ally": True, "is_opponent": False,
            },
            {
                "name_a": NAMES[2], "name_b": NAMES[3],
                "agreement_rate": 0.35, "shared_votes": 80,
                "is_ally": False, "is_opponent": True,
            },
        ]
    }


def build_trends() -> dict:
    return {
        "contestation": [
            {
                "year": year, "total_carried": 100 + year,
                "total_with_dissent": 10, "contestation_rate": 0.1,
                "most_contested": ["Placeholder Topic A", "Placeholder Topic B"],
            }
            for year in range(2020, 2024)
        ],
        "topics": {
            "2020": {"Placeholder Topic A": 5, "Placeholder Topic B": 3},
            "2021": {"Placeholder Topic A": 7, "Placeholder Topic B": 4},
        },
    }


def build_engagement() -> list:
    return [
        {"year": year, "public_questions": 10 + year % 5, "deputations": 2, "petitions": 1}
        for year in range(2020, 2024)
    ]


def build_planning() -> dict:
    def _group(n, approved):
        refused = n - approved
        return {
            "n": n, "approved": approved, "refused": refused,
            "approval_pct": round(approved / n * 100, 1),
        }

    return {
        "trend": [
            {
                "year": year, "n_applications": 50, "decided": 45,
                "approved": 40, "refused": 5, "approval_pct": 88.9,
            }
            for year in range(2020, 2024)
        ],
        "objections": {
            "with_objection": _group(20, 10),
            "no_objection": _group(80, 76),
        },
    }


def build_dissent() -> dict:
    return {
        "profiles": [
            {
                "name": name, "total_votes_on_carried": 200 - i * 10,
                "against_count": 15 + i, "dissent_rate": 0.08 + i * 0.01,
                "is_active": True, "top_dissent_tags": ["Placeholder Topic A"],
            }
            for i, name in enumerate(NAMES)
        ],
        "coalitions": [{"name_a": NAMES[0], "name_b": NAMES[1], "shared_dissent": 6}],
        "by_tag": [
            {"tag": "Placeholder Topic A", "total_carried": 90, "contested": 12, "contestation_rate": 0.13}
        ],
    }


def build_declared() -> dict:
    def _decl(i):
        return {
            "date": f"2022-0{i + 1}-15", "item": f"{i + 1}.1", "title": "Placeholder Agenda Item",
            "interest_type": "financial", "what": "Placeholder interest description.",
            "action": "Stepped out", "must_leave": True, "quote": FAKE_QUOTE,
        }

    return {
        "declared_total": 60, "declared_recused": 40, "declared_recusal_pct": 66.7,
        "declared_against_pct": 5.0,
        "baseline_total": 5000, "baseline_recusal_pct": 3.9, "baseline_against_pct": 25.0,
        "profiles": [
            {
                "name": name, "declared_votes": 15 - i, "recused": 10 - i,
                "recusal_rate": 0.66, "is_active": True,
                "declarations": [_decl(i)],
            }
            for i, name in enumerate(NAMES)
        ],
    }


def build_tenders() -> dict:
    def _award(i):
        return {
            "date": f"2021-0{i + 1}-01", "description": "Placeholder tender description",
            "amount": 250000 * (i + 1), "reference": f"T{1000 + i}",
            "is_confidential": i == 0, "quote": FAKE_QUOTE,
        }

    contractors = [
        {"name": "Placeholder Contractor Ltd", "n_awards": 3, "total_amount": 750000, "awards": [_award(0)]},
        {"name": "Example Constructions Pty", "n_awards": 2, "total_amount": 500000, "awards": [_award(1)]},
    ]
    return {
        "total_awards": 50, "total_amount": 15_000_000,
        "named_awards": 40, "named_amount": 10_000_000,
        "redacted_awards": 10, "redacted_amount": 5_000_000,
        "distinct_named": 12, "top10_amount": 8_000_000, "top10_share": 53.3,
        "contractors": contractors,
    }


def build_dose() -> dict:
    def _app(i, outcome):
        return {
            "reference": f"DA{100 + i}", "description": "Placeholder development application",
            "address": "1 Placeholder Street, Example WA", "n_objectors": i,
            "outcome": outcome, "quote": FAKE_QUOTE,
        }

    def _bucket(label, n, refused, refusal_pct, app):
        return {
            "label": label, "n": n, "refused": refused,
            "refusal_pct": refusal_pct, "n_shown": 1, "apps": [app],
        }

    buckets = [
        _bucket("0", 100, 5, 5.0, _app(0, "approved")),
        _bucket("1", 40, 4, 10.0, _app(1, "approved")),
        _bucket("2-4", 20, 4, 20.0, _app(3, "refused")),
        _bucket("5+", 5, 3, 60.0, _app(6, "refused")),
    ]
    return {
        "total_decided": 165, "max_objections": 8,
        "headline_examples": ["Placeholder headline example about objection dose-response."],
        "buckets": buckets,
    }


def build_transparency() -> dict:
    def _item(i):
        return {
            "kind": "tender", "description": "Placeholder confidential item",
            "amount": 100000 * (i + 1), "date": f"2021-0{i + 1}-01", "quote": FAKE_QUOTE,
        }

    return {
        "pre_era_pct": 4.0, "peak_year": 2022, "peak_pct": 12.5,
        "category_totals": {
            "tender": {"total": 200, "confidential": 20},
            "other_item": {"total": 150, "confidential": 10},
        },
        "years": [
            {
                "year": year, "total": 100, "confidential": 5,
                "confidential_pct": 5.0, "n_shown": 1, "items": [_item(0)],
            }
            for year in range(2020, 2024)
        ],
    }


def build_tenure() -> dict:
    return {
        "median_years": 6.5, "n_councillors": len(NAMES),
        "histogram": {"0-4": 1, "4-8": 2, "8-12": 1},
        "profiles": [
            {
                "name": name, "years": 4 + i * 2, "n_votes": 300 - i * 20,
                "first": "2018-01-01", "last": "2026-01-01", "is_active": True,
            }
            for i, name in enumerate(NAMES)
        ],
    }


def build_mayoral() -> dict:
    def _motion(i):
        return {
            "title": "Placeholder Mayoral Motion", "date": f"2021-0{i + 1}-01",
            "votes_for": 10, "votes_against": 2, "quote": FAKE_QUOTE,
        }

    return {
        "mayor_moved": 40, "mayor_carried_pct": 97.5, "mayor_contest_pct": 12.0,
        "other_moved": 300, "other_carried_pct": 90.0, "other_contest_pct": 22.0,
        "contest_factor": 1.8,
        "per_mayor": [
            {
                "name": MAYOR, "carried": 39, "contested": 5,
                "contest_pct": 12.8, "n_shown": 1, "motions": [_motion(0)],
            }
        ],
    }


def build_power() -> dict:
    def _vote(i):
        return {
            "date": f"2021-0{i + 1}-01", "item": f"{i + 1}.1", "title": "Placeholder Contested Motion",
            "choice": "For", "outcome": "Carried", "won": True, "margin": 4, "quote": FAKE_QUOTE,
        }

    return {
        "base_carry_rate": 0.92, "base_fail_rate": 0.08, "n_contested": 500,
        "profiles": [
            {
                "name": name, "n": 100 - i * 5, "win_rate": 0.9 - i * 0.02,
                "dissent_rate": 0.05 + i * 0.01, "dissent_n": 5 + i,
                "dissent_effectiveness": 0.2, "is_active": True,
                "n_shown": 1, "votes": [_vote(i)],
            }
            for i, name in enumerate(NAMES)
        ],
        "over_time": [
            {
                "name": name,
                "points": [
                    {"term": f"{y}-{y + 2}", "win_rate": 0.85 + i * 0.01, "n": 50}
                    for i, y in enumerate((2016, 2020, 2024))
                ],
            }
            for name in NAMES[:2]
        ],
    }


def build_recusal() -> dict:
    def _decl(i):
        return {
            "date": f"2022-0{i + 1}-01", "item": f"{i + 1}.1", "councillor": NAMES[i % len(NAMES)],
            "action": "Stepped out", "what": "Placeholder interest description.", "quote": FAKE_QUOTE,
        }

    return {
        "inquiry_window": [2022, 2023],
        "must_leave_pre_pct": 92.0, "must_leave_pre_n": 50,
        "must_leave_inquiry_pct": 60.0, "must_leave_inquiry_n": 20,
        "must_leave_post_pct": 88.0, "must_leave_post_n": 30,
        "financial_inquiry_pct": 55.0, "financial_inquiry_n": 15,
        "financial_post_pct": 85.0, "financial_post_n": 25,
        "impartiality_post_declared": 40, "impartiality_post_recusal_pct": 10.0,
        "by_type_era": [
            {
                "interest_type": "financial", "era": "post", "declared": 25, "recused": 21,
                "recusal_pct": 84.0, "n_shown": 1, "declarations": [_decl(0)],
            }
        ],
        "by_year": [
            {
                "year": year, "must_leave_declared": 10, "must_leave_recused": 8,
                "must_leave_pct": 80.0, "declared_share_pct": 15.0,
            }
            for year in range(2020, 2024)
        ],
        "drivers": [{"name": name, "stayed": 3 + i, "total": 20} for i, name in enumerate(NAMES[:2])],
    }


def build_question_responsiveness() -> dict:
    def _q(i):
        return {
            "date": f"2021-0{i + 1}-01", "questioner": "Placeholder Resident",
            "question": "Placeholder public question text.", "status": "Answered in meeting",
            "fielded_by": NAMES[0], "quote": FAKE_QUOTE,
        }

    return {
        "inquiry_window": [2022, 2023],
        "total": 300, "answered": 220, "on_notice": 60, "blank": 20,
        "answered_pct": 73.3, "on_notice_pct": 20.0,
        "pre_pct": 15.0, "pre_n": 100,
        "inquiry_pct": 35.0, "inquiry_n": 80,
        "post_pct": 18.0, "post_n": 120,
        "peak_year": 2022, "peak_pct": 38.0,
        "by_era": [
            {
                "era": "post", "answered": 90, "on_notice": 22, "blank": 8,
                "on_notice_pct": 18.3, "n_shown": 1, "questions": [_q(0)],
            }
        ],
        "by_year": [
            {"year": year, "answered": 50, "on_notice": 12, "n_nonblank": 62, "on_notice_pct": 19.4}
            for year in range(2020, 2024)
        ],
    }


def build_sponsorship() -> dict:
    def _edge(a, b, kind):
        return {
            "era_label": "Placeholder Era", "name_a": a, "name_b": b,
            "sponsorships": 15, "lift": 1.4, "agree_pct": 0.88, "agree_n": 60, "kind": kind,
        }

    return {
        "alliances": [_edge(NAMES[0], NAMES[1], "alliance")],
        "procedural": [_edge(NAMES[2], NAMES[3], "procedural")],
        "convergence_high_agree": 0.9, "convergence_low_agree": 0.4,
        "oldguard_label": "Placeholder Old Guard Era",
        "oldguard_unanimous_pct": 76.0,
        "oldguard_nodes": [{"name": n, "moved": 20, "seconded": 15, "in_core": True} for n in NAMES[:2]],
        "oldguard_edges": [_edge(NAMES[0], NAMES[1], "mixed")],
        "eras": [
            {
                "label": "Placeholder Era", "year_from": 2018, "year_to": 2022,
                "n_events": 400, "n_active": 10, "cluster_size": 4,
                "core_names": NAMES[:2], "structure": "Placeholder structure description",
            }
        ],
    }


def build_overview() -> dict:
    return {
        "span": "2020-2026 (placeholder)",
        "n_minutes": 100, "n_documents": 120,
        "confidential_pre_pct": 4.0, "confidential_peak_pct": 12.5, "confidential_peak_year": 2022,
        "recusal_inquiry_pct": 60.0, "recusal_post_pct": 88.0,
        "financial_inquiry_pct": 55.0, "financial_post_pct": 85.0,
        "base_carry_pct": 92.0, "n_contested": 500,
        "win_min_pct": 80.0, "win_max_pct": 95.0,
        "sponsor_conv_high": 90, "sponsor_conv_low": 40,
        "oldguard_unanimous_pct": 76.0,
        "declared_stay_pct": 33.3,
        "impartiality_post_declared": 40, "impartiality_post_recusal_pct": 10.0,
        "tenure_median_years": 6.5, "tenure_15plus": 1,
        "tenure_top_name": NAMES[0], "tenure_top_years": 18,
        "officer_matched": 18, "officer_diverged": 2, "officer_compliance_pct": 90.0,
        "dose_0_refusal_pct": 5.0, "dose_5plus_refusal_pct": 60.0,
        "tender_total_m": 15.0, "tender_redacted_m": 5.0, "tender_top10_share_pct": 53.3,
        "mayor_contest_pct": 12.0, "other_contest_pct": 22.0,
        "conf_dev_pct": 15.0, "conf_base_pct": 8.0,
        "pq_pre_pct": 15.0, "pq_inquiry_pct": 35.0, "pq_post_pct": 18.0,
        "pq_peak_pct": 38.0, "pq_peak_year": 2022,
    }


def build_councillors() -> dict:
    by_name = {}
    for i, name in enumerate(NAMES):
        by_name[name] = {
            "name": name, "slug": name.lower().replace(" ", "-"),
            "is_active": True, "tenure_years": 4 + i * 2,
            "first_vote": "2018-01-01", "last_vote": "2026-01-01",
            "n_votes": 300 - i * 20,
            "roles": ["Mayor"] if name == MAYOR else ["Councillor"],
            "n_contested": 100 - i * 5, "win_rate": 0.9 - i * 0.02,
            "dissent_rate": 0.05 + i * 0.01, "dissent_n": 5 + i, "dissent_effectiveness": 0.2,
            "n_declarations": 15 - i, "n_recused": 10 - i, "recusal_rate": 0.66,
            "declarations": [{
                "date": "2022-01-15", "item": "1.1", "title": "Placeholder Agenda Item",
                "interest_type": "financial", "what": "Placeholder interest description.",
                "action": "Stepped out", "must_leave": True, "quote": FAKE_QUOTE,
            }],
            "dissent_votes": [{
                "date": "2021-01-01", "item": "1.1", "title": "Placeholder Contested Motion",
                "choice": "Against", "outcome": "Carried", "won": False, "margin": 2, "quote": FAKE_QUOTE,
            }],
            "moved": 20 - i, "seconded": 15 - i,
            "top_partners": [{"name": NAMES[(i + 1) % len(NAMES)], "count": 12}],
        }
    return {"by_name": by_name}


SNAPSHOTS = {
    "scorecard": build_scorecard,
    "interests": build_interests,
    "divergence": build_divergence,
    "co-movers": build_co_movers,
    "alignment": build_alignment,
    "trends": build_trends,
    "engagement": build_engagement,
    "planning": build_planning,
    "dissent": build_dissent,
    "declared": build_declared,
    "tenders": build_tenders,
    "dose": build_dose,
    "transparency": build_transparency,
    "tenure": build_tenure,
    "mayoral": build_mayoral,
    "power": build_power,
    "recusal": build_recusal,
    "question-responsiveness": build_question_responsiveness,
    "sponsorship": build_sponsorship,
    "overview": build_overview,
    "councillors": build_councillors,
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing {len(SNAPSHOTS)} placeholder snapshots to {OUTPUT_DIR}...")
    for name, builder in SNAPSHOTS.items():
        _write(name, builder())
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps({
        "published_at": GENERATED_AT,
        "council": "cambridge",
        "placeholder": True,
        "note": "Bootstrap placeholder data — see scripts/generate_placeholder_data.py. "
                "Not produced by council publish; replace via the real draft/publish pipeline.",
        "snapshots": list(SNAPSHOTS),
    }, indent=2))
    print("Done.")


if __name__ == "__main__":
    main()
