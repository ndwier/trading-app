"""
Real-time insider enrichment - fetch actual biographical data on demand.
"""

import requests
from bs4 import BeautifulSoup
import logging
from typing import Dict, Optional
import json

logger = logging.getLogger(__name__)


class InsiderEnrichment:
    """Fetch real information about insiders in real-time."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def enrich_politician(self, name: str, state: str = None) -> Dict:
        """
        Enrich politician data using Congress.gov API and other sources.
        """
        enriched = {
            'bio': None,
            'committees': [],
            'leadership': None,
            'why_matters': None
        }
        
        try:
            # Try ProPublica Congress API (free)
            # First, search for the member
            search_name = name.replace(' ', '+')
            
            # Try to get from Wikipedia first for bio
            wiki_data = self._get_wikipedia_summary(name)
            if wiki_data:
                enriched['bio'] = wiki_data['summary']
                enriched['why_matters'] = wiki_data['why_matters']
            
            # Try GovTrack API for committee info
            govtrack_data = self._get_govtrack_info(name)
            if govtrack_data:
                enriched['committees'] = govtrack_data.get('committees', [])
                enriched['leadership'] = govtrack_data.get('leadership')
            
            # Generate "why matters" based on committees
            if enriched['committees']:
                enriched['why_matters'] = self._generate_politician_significance(
                    name, enriched['committees'], enriched.get('leadership')
                )
            
        except Exception as e:
            logger.error(f"Error enriching politician {name}: {e}")
        
        return enriched
    
    def enrich_corporate_insider(self, name: str, company: str = None) -> Dict:
        """
        Enrich corporate insider data.
        """
        enriched = {
            'bio': None,
            'company': company,
            'role': None,
            'why_matters': None
        }
        
        try:
            # Try Wikipedia
            wiki_data = self._get_wikipedia_summary(name)
            if wiki_data:
                enriched['bio'] = wiki_data['summary']
                enriched['why_matters'] = wiki_data['why_matters']
            
            # If no Wikipedia, generate generic but informative text
            if not enriched['why_matters']:
                if company:
                    enriched['why_matters'] = (
                        f"{name} is a corporate insider at {company}. "
                        "As an insider, they have access to non-public information about "
                        "company performance, upcoming products, and strategic decisions. "
                        "Their trades can signal confidence or concern about the company's future."
                    )
                else:
                    enriched['why_matters'] = (
                        f"{name} is a corporate insider with privileged access to company "
                        "information. Their trading patterns often precede significant company "
                        "announcements or financial results."
                    )
            
        except Exception as e:
            logger.error(f"Error enriching corporate insider {name}: {e}")
        
        return enriched
    
    def _normalize_name(self, name: str) -> list:
        """
        Generate different name variations to try.
        
        Examples:
        "Powell Dina H." -> ["Powell Dina H.", "Dina Powell", "Dina H. Powell"]
        "KIMMITT ROBERT M" -> ["Robert Kimmitt", "Robert M Kimmitt", "KIMMITT ROBERT M"]
        """
        variations = [name]  # Always try original first
        
        # Remove periods
        no_periods = name.replace('.', '')
        if no_periods != name:
            variations.append(no_periods)
        
        # Try title case
        title_case = name.title()
        if title_case != name:
            variations.append(title_case)
        
        # Try reversing "Last First M." to "First Last"
        parts = name.replace('.', '').split()
        if len(parts) >= 2:
            # If looks like "Last First Middle", try "First Last"
            if parts[0][0].isupper() and parts[1][0].isupper():
                variations.append(f"{parts[1]} {parts[0]}")
                
                # Try "First Middle Last" too
                if len(parts) >= 3:
                    variations.append(f"{parts[1]} {parts[2]} {parts[0]}")
                    variations.append(f"{parts[1]} {parts[0]}")  # First Last (no middle)
        
        return variations
    
    def _get_wikipedia_summary(self, name: str) -> Optional[Dict]:
        """
        Fetch Wikipedia summary for a person.
        """
        # Try multiple name variations
        name_variations = self._normalize_name(name)
        
        for variation in name_variations:
            try:
                # Wikipedia API
                url = "https://en.wikipedia.org/w/api.php"
                params = {
                    'action': 'query',
                    'format': 'json',
                    'titles': variation,
                    'prop': 'extracts',
                    'exintro': True,
                    'explaintext': True
                }
                
                response = self.session.get(url, params=params, timeout=5)
                data = response.json()
                
                pages = data.get('query', {}).get('pages', {})
                if not pages:
                    continue  # Try next variation
                
                page = list(pages.values())[0]
                if 'extract' not in page or not page['extract']:
                    continue  # Try next variation
                
                extract = page['extract']
                
                # Get first 2-3 sentences
                sentences = extract.split('. ')[:3]
                summary = '. '.join(sentences) + '.'
                
                # Generate why_matters from the summary
                why_matters = self._extract_significance(summary)
                
                logger.info(f"Wikipedia found for {name} using variation: {variation}")
                return {
                    'summary': summary,
                    'why_matters': why_matters
                }
                
            except Exception as e:
                logger.debug(f"Wikipedia lookup failed for {name} variation '{variation}': {e}")
                continue  # Try next variation
        
        # If all variations failed
        return None
    
    def _get_govtrack_info(self, name: str) -> Optional[Dict]:
        """
        Get committee and leadership info from GovTrack.
        """
        # Try multiple name variations
        name_variations = self._normalize_name(name)
        
        for variation in name_variations:
            try:
                # GovTrack's person search
                search_url = f"https://www.govtrack.us/api/v2/person"
                params = {
                    'name': variation,
                    'current': 'true'
                }
                
                response = self.session.get(search_url, params=params, timeout=5)
                data = response.json()
                
                if not data.get('objects'):
                    continue  # Try next variation
                
                person = data['objects'][0]
                person_id = person['id']
                
                # Get their roles/committees
                roles_url = f"https://www.govtrack.us/api/v2/role"
                roles_params = {
                    'person': person_id,
                    'current': 'true'
                }
                
                roles_response = self.session.get(roles_url, params=roles_params, timeout=5)
                roles_data = roles_response.json()
                
                committees = []
                leadership = None
                
                if roles_data.get('objects'):
                    role = roles_data['objects'][0]
                    
                    # Get committees
                    if 'committees' in role:
                        for committee in role.get('committees', []):
                            committees.append({
                                'name': committee.get('name', 'Unknown Committee'),
                                'role': 'Member'
                            })
                    
                    # Check for leadership positions
                    if role.get('leadership_title'):
                        leadership = role['leadership_title']
                
                logger.info(f"GovTrack found for {name} using variation: {variation}")
                return {
                    'committees': committees,
                    'leadership': leadership
                }
                
            except Exception as e:
                logger.debug(f"GovTrack lookup failed for {name} variation '{variation}': {e}")
                continue  # Try next variation
        
        # If all variations failed
        return None
    
    def _extract_significance(self, text: str) -> str:
        """
        Extract why someone matters from their bio.
        """
        text_lower = text.lower()
        
        # Look for key phrases
        if 'senator' in text_lower or 'senate' in text_lower:
            return "As a U.S. Senator, their trades can signal legislative priorities and upcoming policy changes that could affect entire industries."
        elif 'representative' in text_lower or 'congress' in text_lower:
            return "As a member of Congress, their trades may reflect knowledge of upcoming legislation and regulatory changes that haven't been publicly announced."
        elif 'deputy national security' in text_lower or 'national security advisor' in text_lower:
            return "With access to classified national security information, their trades may signal geopolitical developments or government contracts before public disclosure."
        elif 'secretary of' in text_lower or 'cabinet' in text_lower:
            return "As a cabinet member, they have access to policy decisions and regulatory changes that can significantly impact markets before public announcement."
        elif 'white house' in text_lower or 'administration' in text_lower:
            return "Their White House position provides access to policy decisions and economic data before public release, making their trades particularly insightful."
        elif 'goldman sachs' in text_lower or 'investment bank' in text_lower or 'wall street' in text_lower:
            return "Their Wall Street background and high-level connections provide unique insights into market movements and corporate transactions."
        elif 'ceo' in text_lower or 'chief executive' in text_lower:
            return "As CEO, they have the deepest insider knowledge of company strategy, financial performance, and upcoming announcements that can move markets."
        elif 'chairman' in text_lower or 'chair' in text_lower or 'board' in text_lower:
            return "As a board member, they have fiduciary access to strategic decisions, M&A activity, and confidential company information before public disclosure."
        elif 'director' in text_lower:
            return "As a director, they have access to confidential company information and strategic decisions that can inform high-probability trades."
        else:
            return "Their position provides privileged access to non-public information that can influence trading decisions and market movements."
    
    def _generate_politician_significance(self, name: str, committees: list, leadership: str = None) -> str:
        """
        Generate significance text based on committees.
        """
        if leadership:
            sig = f"{name} holds the leadership position of {leadership}. "
        else:
            sig = f"{name} is a member of Congress"
        
        if committees:
            committee_names = [c['name'] for c in committees[:2]]
            sig += f" serving on the {' and '.join(committee_names)}. "
            
            # Add context based on committee
            for committee in committees:
                c_name = committee['name'].lower()
                if 'energy' in c_name:
                    sig += "Their committee position gives them advance knowledge of energy policy and regulation changes. "
                    break
                elif 'finance' in c_name or 'banking' in c_name:
                    sig += "Their committee role provides insight into financial regulation and economic policy. "
                    break
                elif 'intelligence' in c_name:
                    sig += "Their intelligence committee position gives them classified information about national security matters. "
                    break
                elif 'defense' in c_name or 'armed services' in c_name:
                    sig += "Their defense committee role provides insight into military contracts and defense spending. "
                    break
                elif 'technology' in c_name or 'telecommunications' in c_name:
                    sig += "Their committee position gives them advance knowledge of tech regulation and policy. "
                    break
        
        sig += "Congressional trades often precede major policy announcements and regulatory changes."
        
        return sig


def get_enriched_insider_data(name: str, filer_type: str, company: str = None, state: str = None) -> Dict:
    """
    Main function to get enriched insider data.
    """
    enricher = InsiderEnrichment()
    
    if filer_type.lower() == 'politician':
        return enricher.enrich_politician(name, state)
    else:
        return enricher.enrich_corporate_insider(name, company)

