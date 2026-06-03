import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read_last_lines(filepath, n=100):
    if not os.path.exists(filepath):
        print(f"{filepath} does not exist.")
        return
    print(f"=== Last {n} lines of {filepath} ===")
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        for line in lines[-n:]:
            print(line, end="")

def main():
    read_last_lines(os.path.join(ROOT, 'data', 'background_scraper.log'), 100)
    print("\n")
    read_last_lines(os.path.join(ROOT, 'errors.log'), 50)

if __name__ == '__main__':
    main()
