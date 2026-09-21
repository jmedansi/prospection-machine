import os
import re

functions = [
    "_drpNextMonth", "_drpPrevMonth", "_drpRender", "_drpReset", "_drpToggle",
    "addPlannedCampaign", "changeCampaignPage", "clearGlobalDate", "closeModal",
    "closeSidePanel", "deleteLead", "deleteSelectedLeads", "exportFilteredLeads",
    "generateSelectedEmails", "launchScraperFromModal", "launchSelectedAudits",
    "loadPlanning", "loadRoiData", "mAddPlanned", "mBatchAudit", "mBatchDelete",
    "mBatchEmail", "mCloseSheet", "mExitSelectMode", "mFabAction", "mLaunchScraper",
    "mRunHealth", "mSaveSettings", "mSheetTab", "mobileNav", "mobileRefresh", "nav",
    "openScraperModal", "purgeZeroAvis", "pushSelectedToGitHub", "refreshAll",
    "refreshCampaignData", "resetAllData", "retryFailedAudits", "runHealthCheck",
    "saveEmail", "saveIdentity", "saveLead", "saveSettings", "sendApprovedEmails",
    "setCRMFilter", "showSniperLaunchModal", "sniperGenerateEmails",
    "sniperLaunchBodacc", "sniperLaunchJobs", "sniperLaunchTech", "sniperLoadStatus",
    "sniperPollImap", "sniperSendStep1", "sniperSetQuota", "switchPanelTab",
    "testConnections", "toggleSidebar", "toggleTheme"
]

# Note: stopPropagation is a native event method, usually called as event.stopPropagation()

js_files = [
    "dashboard/static/js/modules/dashboard_core.js",
    "dashboard/static/js/api.js",
    "dashboard/static/js/ui.js",
    "dashboard/static/js/modules/collecte.js",
    "dashboard/static/js/modules/audits.js",
    "dashboard/static/js/modules/rapports.js",
    "dashboard/static/js/modules/settings.js",
    "dashboard/static/js/modules/planificateur.js",
    "dashboard/static/js/modules/sniper.js"
]

results = {f: None for f in functions}

for js_file in js_files:
    if not os.path.exists(js_file):
        print(f"File not found: {js_file}")
        continue
    with open(js_file, 'r', encoding='utf-8') as f_in:
        content = f_in.read()
        for f in functions:
            # Match function f() or function f (
            pattern = re.compile(rf'function\s+{f}\s*\(')
            if pattern.search(content):
                if results[f] is None:
                    results[f] = js_file
                else:
                    results[f] = f"{results[f]}, {js_file}"

print("FUNCTION VERIFICATION RESULTS:")
missing = []
for f, loc in results.items():
    if loc:
        print(f"[OK] {f} found in {loc}")
    else:
        print(f"[MISSING] {f}")
        missing.append(f)

print("\nMISSING FUNCTIONS:")
for f in missing:
    print(f)
