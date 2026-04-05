"""V2 validation: use SECULAR occupation exclusion list instead of Buddhist inclusion.

Strategy:
- Delete persons whose occupations are CLEARLY secular (actor, athlete, politician, etc.)
- AND they don't have any Buddhist clergy occupation at all
- Keep people who have at least one religious/monastic occupation, even alongside secular ones
"""
import json

# Clearly secular occupations (NOT Buddhist clergy)
SECULAR_OCCUPATIONS = {
    # Entertainment
    "Q33999",    # actor
    "Q2526255",  # film director
    "Q177220",   # singer
    "Q639669",   # musician
    "Q753110",   # songwriter
    "Q10800557", # film actor
    "Q10798782", # television actor
    "Q3282637",  # film producer
    "Q1053574",  # screenwriter
    "Q465501",   # martial artist
    "Q177220",   # singer
    "Q2259451",  # stage actor
    "Q3455803",  # director
    "Q970153",   # voice actor
    "Q4964182",  # philosopher (too broad, often secular)
    "Q18844224", # politician (non-Buddhist)
    "Q483501",   # artist
    # Sports
    "Q937857",   # football player
    "Q2066131",  # athlete
    "Q3665646",  # basketball player
    "Q19204627", # American football player
    "Q1415090",  # martial arts competitor
    # Politics/Government
    "Q82955",    # politician
    "Q372436",   # statesperson
    "Q189290",   # military officer
    "Q189290",   # officer
    "Q47064",    # militant
    "Q2259532",  # diplomat
    "Q1055894",  # parliamentary assistant
    "Q30185",    # governor
    # Business
    "Q43845",    # businessperson
    "Q131512",   # farmer
    "Q4964182",  # philosopher
    "Q201788",   # historian
    # Royalty/nobility
    "Q12362622", # emperor
    "Q39018",    # duke
    "Q12323521", # king
    # Other clearly non-Buddhist
    "Q214917",   # playwright
    "Q28389",    # screenwriter
    "Q578478",   # professional wrestler
    "Q855091",   # guitarist
    "Q15981151", # beauty pageant contestant
    "Q6665249",  # television producer
    "Q3578589",  # film editor
    "Q13219637", # stunt performer
    "Q9017214",  # aikido practitioner
    "Q3282637",  # film producer
    "Q18814623", # autobiographer
    "Q13590141", # record producer
    "Q4610556",  # model
    "Q11338576", # boxer
    "Q36834",    # composer
    "Q81096",    # engineer
    "Q131524",   # entrepreneur
    "Q212238",   # civil servant
    "Q13582652", # child actor
    "Q2259532",  # diplomat
    "Q222749",   # lawyer
    "Q169470",   # physicist
    "Q193391",   # Note: this was mis-labeled as Buddhist teacher, actually theologian — keep as ambiguous
    "Q188094",   # economist
    "Q864380",   # anthropologist
}

# Clearly Buddhist/religious occupations — having ANY of these keeps the person
BUDDHIST_OCCUPATIONS = {
    "Q4263842",   # Buddhist monk
    "Q1662844",   # Buddhist priest
    "Q161598",    # Buddhist nun
    "Q2018370",   # Buddhist philosopher
    "Q3336976",   # lama
    "Q208974",    # tulku
    "Q12353098",  # Buddhist scholar
    "Q21160022",  # Tibetan Buddhist monk
    "Q170790",    # monk
    "Q171087",    # nun
    "Q34679",     # priest (generic religious)
    "Q854979",    # Buddhist nun variant
    "Q854997",    # religious leader
    "Q1234713",   # theologian
    "Q38571",     # cleric
    "Q1094016",   # minister of religion
    "Q11513337",  # philosopher-monk
    "Q193391",    # "religious official" (sometimes tagged buddhist)
}


def main():
    with open("data/buddhist_persons.json", encoding="utf-8") as f:
        records = json.load(f)

    # Re-use the previously fetched occupations
    # (we could save them separately, but let's refetch via persons_to_delete.json metadata)
    with open("data/persons_not_buddhist.json", encoding="utf-8") as f:
        flagged = json.load(f)

    flagged_by_qid = {x["wikidata_id"]: x for x in flagged}

    really_delete = []
    revive_as_buddhist = []

    for rec in records:
        wid = rec["wikidata_id"]
        if wid not in flagged_by_qid:
            continue  # Was kept in first pass, do nothing
        entry = flagged_by_qid[wid]
        occs = set(entry["occupations"])

        has_buddhist = bool(occs & BUDDHIST_OCCUPATIONS)
        has_secular = bool(occs & SECULAR_OCCUPATIONS)

        if has_buddhist:
            revive_as_buddhist.append(wid)
        elif has_secular:
            really_delete.append(wid)
        # else: ambiguous occupations only — keep by default (conservative)

    print(f"Flagged by first pass: {len(flagged_by_qid)}")
    print(f"Actually delete (secular):      {len(really_delete)}")
    print(f"Revive (has Buddhist occ):      {len(revive_as_buddhist)}")
    print(f"Keep (ambiguous):               {len(flagged_by_qid) - len(really_delete) - len(revive_as_buddhist)}")

    # Sample of really-delete
    print("\n=== Sample actual deletions (secular) ===")
    for wid in really_delete[:20]:
        entry = flagged_by_qid[wid]
        print(f"  {entry['name_zh']} | {entry['name_en']} | {entry['occupations']}")

    # Save
    with open("data/persons_delete_final.json", "w", encoding="utf-8") as f:
        json.dump(really_delete, f)
    print(f"\nSaved → data/persons_delete_final.json ({len(really_delete)} Q-IDs)")

    print("\n=== Sample 'revive' (Buddhist clergy miscategorized) ===")
    for wid in revive_as_buddhist[:20]:
        entry = flagged_by_qid[wid]
        print(f"  {entry['name_zh']} | {entry['name_en']} | {entry['occupations']}")


if __name__ == "__main__":
    main()
