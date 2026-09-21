import os

file_path = r'd:\prospection-machine\dashboard\static\js\modules\dashboard_core.js'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Keep only up to line 1703 (index 1702)
# But let's be sure where we stop. We stop before the "MOBILE APP CONTROLLER" block.
clean_lines = []
for line in lines:
    if '// MOBILE APP CONTROLLER' in line:
        break
    clean_lines.append(line)

# Also fix the nav() function at the beginning
# We search for the function nav(page, el) { ... } block and replace it
# It starts around line 13-14

new_content = "".join(clean_lines)

# Robust nav function replacement
old_nav_start = "        function nav(page, el) {"
# We need to find the end of the broken nav function. 
# It currently ends around line 59.

import re
pattern = r'function nav\(page, el\) \{[\s\S]*?document\.getElementById\(\'PT\'\)\.textContent = titles\[page\] \|\| page;\s+\}'
replacement = """function nav(page, el) {
            console.log('Nav to:', page);
            localStorage.setItem('pm_current_page', page);
            
            // Sync UI Active States
            document.querySelectorAll('.ni, .mobile-nav-item').forEach(n => n.classList.remove('active'));
            
            const desktopNav = document.getElementById('nav-' + page);
            if(desktopNav) desktopNav.classList.add('active');
            
            const mobileNavEl = document.getElementById('nav-' + page + '-m');
            if(mobileNavEl) mobileNavEl.classList.add('active');

            // Switch Section
            document.querySelectorAll('.v-section').forEach(s => s.classList.remove('active'));
            const target = document.getElementById('section-' + page);
            if(target) {
                target.classList.add('active');
                _loadDataForSection(page);
            }
            
            const titles = {
                cockpit: 'Cockpit', campagne: 'Campagnes', tracking: 'Tracking',
                planificateur: 'Planning', settings: 'Paramètres', sniper: 'Sniper B2B'
            };
            document.getElementById('PT').textContent = titles[page] || page;
        }"""

new_content = re.sub(pattern, replacement, new_content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Dashboard Core JS cleaned and unified.")
