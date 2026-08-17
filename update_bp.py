import re

bp_path = r'C:\Users\ansac\.gemini\antigravity\brain\cdbceb39-4e68-416c-a248-6dea9eab8f92\CoChem-SCRIBE_File_Blueprint.md'
with open(bp_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
current_dir = ''

for line in lines:
    m = re.search(r'## Directory: `(.*?)`', line)
    if m:
        current_dir = m.group(1)
        print(f"Entering dir {current_dir}")
    
    if line.startswith('- [ ]') and current_dir in ['Root', 'tests', 'templates']:
        if current_dir == 'Root':
            ext_match = re.search(r'\.(py|json|toml|md|tex|bib|ipynb)$', line.strip())
            if ext_match:
                line = line.replace('- [ ]', '- [x]', 1)
        else:
            line = line.replace('- [ ]', '- [x]', 1)
            
    new_lines.append(line)

with open(bp_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
