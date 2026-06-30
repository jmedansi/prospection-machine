with open('dashboard/errors.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print("Tracebacks or errors in dashboard/errors.log:")
in_traceback = False
traceback_lines = []
for i, line in enumerate(lines):
    if "Traceback" in line or "ERROR" in line or "Exception" in line:
        # Print context: 5 lines before and 20 lines after or until empty line
        print(f"--- MATCH AT LINE {i} ---")
        for j in range(max(0, i-5), min(len(lines), i+30)):
            print(f"{j}: {lines[j].strip()}")
        print("-" * 50)
