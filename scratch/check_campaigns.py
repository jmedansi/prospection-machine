# -*- coding: utf-8 -*-
import sqlite3

def main():
    conn = sqlite3.connect('data/prospection.db')
    conn.row_factory = sqlite3.Row
    
    # 1. Total leads and campaigns
    total_leads = conn.execute("SELECT COUNT(*) FROM leads_bruts").fetchone()[0]
    total_camps = conn.execute("SELECT COUNT(*) FROM campagnes").fetchone()[0]
    print(f"Total leads in leads_bruts: {total_leads}")
    print(f"Total campaigns in campagnes: {total_camps}")
    
    # 2. Leads without campaign_id
    leads_no_camp = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE campaign_id IS NULL").fetchone()[0]
    print(f"Leads with campaign_id IS NULL: {leads_no_camp}")
    
    # 3. Campaign details
    print("\nCampaigns in DB:")
    camps = conn.execute("SELECT id, nom, secteur, ville, total_leads, statut, phase FROM campagnes").fetchall()
    for c in camps:
        print(f"  ID: {c['id']} | Name: {c['nom']} | Sector: {c['secteur']} | City: {c['ville']} | total_leads (stored): {c['total_leads']} | status: {c['statut']} | phase: {c['phase']}")
        
    # 4. Campaign IDs referenced in leads_bruts that don't exist in campagnes
    orphans = conn.execute("""
        SELECT DISTINCT campaign_id FROM leads_bruts 
        WHERE campaign_id IS NOT NULL 
          AND campaign_id NOT IN (SELECT id FROM campagnes)
    """).fetchall()
    print(f"\nCampaign IDs in leads_bruts that DO NOT exist in campagnes table: {[r[0] for r in orphans]}")
    
    # 5. Group leads_bruts by campaign_id
    print("\nLeads count by campaign_id in leads_bruts:")
    counts = conn.execute("SELECT campaign_id, COUNT(*) FROM leads_bruts GROUP BY campaign_id").fetchall()
    for r in counts:
        print(f"  campaign_id: {r[0]} -> {r[1]} leads")
        
    conn.close()

if __name__ == "__main__":
    main()
