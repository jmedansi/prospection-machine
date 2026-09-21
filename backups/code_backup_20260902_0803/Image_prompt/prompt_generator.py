import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PromptGenerator:
    """Générateur de prompts pour la création de visuels de prospection."""
    
    def __init__(self):
        self.styles = {
            "premium_web": "photorealistic website mockup, 8k, modern UI/UX, clean layout, vibrant colors, soft lighting, professional photography style",
            "tech_problem": "abstract digital representation of {problem}, glitch effect, red alert colors, cyber security aesthetic, 3d render, octane render",
        }

    def generate_hero_prompt(self, lead_data: Dict[str, Any]) -> str:
        """Génère un prompt pour une maquette de site web améliorée."""
        name = lead_data.get("nom", "Business")
        sector = lead_data.get("secteur", "professionnel")
        
        base_prompt = f"A stunning, modern website hero section for '{name}', a {sector} company. "
        style = self.styles["premium_web"]
        
        return f"{base_prompt} {style} --v 6.0"

    def generate_problem_prompt(self, problem_type: str) -> str:
        """Génère un prompt illustrant un problème technique spécifique."""
        problem_map = {
            "vitesse": "extremely slow loading speed, snail moving on a keyboard, frustrated user",
            "seo": "hidden business in a dark forest, fog, invisible sign, search engine optimization failure",
            "mobile": "broken website on a modern smartphone, distorted layout, non-responsive design",
        }
        
        detail = problem_map.get(problem_type, problem_type)
        style = self.styles["tech_problem"].format(problem=problem_type)
        
        return f"{detail}, {style}"

if __name__ == "__main__":
    # Test simple
    gen = PromptGenerator()
    test_lead = {"nom": "Le Petit Bistrot", "secteur": "Restaurant"}
    print(f"Hero Prompt: {gen.generate_hero_prompt(test_lead)}")
    print(f"Problem Prompt (vitesse): {gen.generate_problem_prompt('vitesse')}")
