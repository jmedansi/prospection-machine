import sys
from synthetiseur.generator_no_site import load_lead
from synthetiseur import mockup_generator

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python run_mockup_for_lead.py <lead_id>')
        sys.exit(2)
    lead_id = int(sys.argv[1])
    lead = load_lead(lead_id)
    print('Generating mockup for lead', lead_id, lead.get('nom'))
    res = mockup_generator.generate_mockup(lead)
    print(res)
