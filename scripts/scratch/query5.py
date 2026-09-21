import sys
import os
sys.path.append('d:/prospection-machine')
from database.repos.leads_repo import leads_repo

lead = leads_repo.get_by_id(1948)
print(lead.get('kanban_status'))
print(lead.get('statut_display'))
