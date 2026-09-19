"""One-off utility: dumps every row of the `questions` table to a JSON file
so it can be imported into another database."""
import json

import db

OUTPUT_PATH = "questions_export.json"


def main():
    client = db.get_client()
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        res = client.table("questions").select("*").range(offset, offset + page_size - 1).execute()
        rows = res.data
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(all_rows)} questions to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
