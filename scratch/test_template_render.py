from envoi import sector_templates, template_renderer
lead={'ceo_prenom':'Jean','nom_societe':'Test SARL','lien_rapport':'https://audit.test/123'}
print('Template mail1 immobilier:')
t=sector_templates.get_template('immobiliere','mail1')
print(t['subject'])
print(template_renderer.render(t['body'], lead))
print('\nRelance_1 generic:')
tr=sector_templates.get_template('','relance_1')
print(tr['subject'])
print(template_renderer.render(tr['body'], lead))
