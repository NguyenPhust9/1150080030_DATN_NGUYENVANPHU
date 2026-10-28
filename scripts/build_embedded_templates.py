import pprint
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "apps" / "rentals" / "templates"
OUTPUT_FILE = BASE_DIR / "apps" / "rentals" / "embedded_templates.py"


def main():
    templates_dict = {}
    for file_path in TEMPLATES_DIR.rglob("*"):
        if file_path.is_file() and file_path.suffix == ".html":
            rel_path = file_path.relative_to(TEMPLATES_DIR).as_posix()
            content = file_path.read_text(encoding="utf-8")
            templates_dict[rel_path] = content

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# Generated from apps/rentals/templates for serverless deployment.\n")
        f.write("TEMPLATES = ")
        pprint.pprint(templates_dict, stream=f, width=120)
        f.write("\n")

    print(f"Successfully generated {OUTPUT_FILE} with {len(templates_dict)} templates.")


if __name__ == "__main__":
    main()

