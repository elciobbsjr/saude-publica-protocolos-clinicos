import json
from pathlib import Path

def generate_json(data, output_path):
    output_path = Path(output_path)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4
        )

    print(f"JSON salvo em: {output_path}")