import sys
import os
sys.path.append('d:/prospection-machine')
from database.repos.leads_repo import leads_repo

leads = leads_repo.get_all(search="supformation")
if leads['leads']:
    print(leads['leads'][0].get('kanban_status'))
    print(leads['leads'][0].get('statut_display'))
