"""Committee assignment scraper for Congress members."""

import logging
import re
from typing import Dict, List, Set
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from config.config import config
from src.database import get_session, Filer, FilerType


class CommitteeScraper:
    """Scraper for congressional committee assignments."""
    
    def __init__(self):
        self.logger = logging.getLogger("committee_scraper")
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    def scrape_all_committees(self) -> Dict[str, List[Dict]]:
        """Scrape all committee assignments."""
        
        results = {
            'house': self._scrape_house_committees(),
            'senate': self._scrape_senate_committees()
        }
        
        return results
    
    def _scrape_house_committees(self) -> List[Dict]:
        """Scrape House committee assignments."""
        
        committees = []
        
        # House committees JSON endpoint (if available) or scrape HTML
        # For now, use a simplified approach with known committees
        house_committees = [
            {"name": "Agriculture", "url": "https://agriculture.house.gov"},
            {"name": "Appropriations", "url": "https://appropriations.house.gov"},
            {"name": "Armed Services", "url": "https://armedservices.house.gov"},
            {"name": "Budget", "url": "https://budget.house.gov"},
            {"name": "Education and Labor", "url": "https://edlabor.house.gov"},
            {"name": "Energy and Commerce", "url": "https://energycommerce.house.gov"},
            {"name": "Financial Services", "url": "https://financialservices.house.gov"},
            {"name": "Foreign Affairs", "url": "https://foreignaffairs.house.gov"},
            {"name": "Homeland Security", "url": "https://homeland.house.gov"},
            {"name": "Intelligence", "url": "https://intelligence.house.gov"},
            {"name": "Judiciary", "url": "https://judiciary.house.gov"},
            {"name": "Oversight and Reform", "url": "https://oversight.house.gov"},
            {"name": "Science, Space, and Technology", "url": "https://science.house.gov"},
            {"name": "Small Business", "url": "https://smallbusiness.house.gov"},
            {"name": "Transportation and Infrastructure", "url": "https://transportation.house.gov"},
            {"name": "Veterans' Affairs", "url": "https://veterans.house.gov"},
            {"name": "Ways and Means", "url": "https://waysandmeans.house.gov"},
        ]
        
        for committee in house_committees:
            try:
                self.logger.info(f"Scraping House {committee['name']} committee")
                members = self._scrape_committee_page(committee['url'], 'house')
                
                if members:
                    committees.append({
                        'name': committee['name'],
                        'chamber': 'House',
                        'members': members
                    })
                    
            except Exception as e:
                self.logger.warning(f"Failed to scrape {committee['name']}: {e}")
        
        return committees
    
    def _scrape_senate_committees(self) -> List[Dict]:
        """Scrape Senate committee assignments."""
        
        committees = []
        
        # Senate committee list
        senate_committees = [
            {"name": "Agriculture, Nutrition, and Forestry", "id": "agriculture"},
            {"name": "Appropriations", "id": "appropriations"},
            {"name": "Armed Services", "id": "armed-services"},
            {"name": "Banking, Housing, and Urban Affairs", "id": "banking"},
            {"name": "Budget", "id": "budget"},
            {"name": "Commerce, Science, and Transportation", "id": "commerce"},
            {"name": "Energy and Natural Resources", "id": "energy"},
            {"name": "Environment and Public Works", "id": "environment"},
            {"name": "Finance", "id": "finance"},
            {"name": "Foreign Relations", "id": "foreign-relations"},
            {"name": "Health, Education, Labor, and Pensions", "id": "help"},
            {"name": "Homeland Security and Governmental Affairs", "id": "homeland"},
            {"name": "Judiciary", "id": "judiciary"},
            {"name": "Rules and Administration", "id": "rules"},
            {"name": "Small Business", "id": "small-business"},
            {"name": "Veterans' Affairs", "id": "veterans"},
            {"name": "Intelligence", "id": "intelligence"},
        ]
        
        for committee in senate_committees:
            try:
                url = f"https://www.senate.gov/committees/committee.htm?id={committee['id']}"
                self.logger.info(f"Scraping Senate {committee['name']} committee")
                members = self._scrape_committee_page(url, 'senate')
                
                if members:
                    committees.append({
                        'name': committee['name'],
                        'chamber': 'Senate',
                        'members': members
                    })
                    
            except Exception as e:
                self.logger.warning(f"Failed to scrape {committee['name']}: {e}")
        
        return committees
    
    def _scrape_committee_page(self, url: str, chamber: str) -> List[str]:
        """Scrape members from a committee page."""
        
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            members = set()
            
            # Try common patterns for member names
            # Look for links to member pages, names in lists, etc.
            
            # Pattern 1: Links containing member names
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').lower()
                text = link.text.strip()
                
                # Check if it looks like a member name
                if (('member' in href or 'biography' in href or '/members/' in href) and 
                    text and len(text.split()) >= 2 and len(text) < 50):
                    members.add(text)
            
            # Pattern 2: Structured lists
            for ul in soup.find_all('ul'):
                for li in ul.find_all('li'):
                    text = li.text.strip()
                    # Clean up common prefixes
                    text = re.sub(r'^(Rep\.|Sen\.|Mr\.|Mrs\.|Ms\.)\s+', '', text)
                    text = re.sub(r'\s+\([RD]-[A-Z]{2}\)', '', text)  # Remove party/state
                    
                    if text and 2 <= len(text.split()) <= 4 and len(text) < 50:
                        members.add(text)
            
            return list(members)
            
        except Exception as e:
            self.logger.error(f"Failed to scrape {url}: {e}")
            return []
    
    def save_committee_data(self, committee_data: Dict):
        """Save committee assignments to database."""
        
        with get_session() as session:
            for chamber_data in [committee_data.get('house', []), committee_data.get('senate', [])]:
                for committee in chamber_data:
                    committee_name = committee['name']
                    chamber = committee['chamber']
                    
                    for member_name in committee['members']:
                        # Find filer in database
                        filer = session.query(Filer).filter(
                            Filer.name.ilike(f"%{member_name}%")
                        ).first()
                        
                        if filer:
                            # Update filer with committee info
                            if not filer.metadata_json:
                                filer.metadata_json = {}
                            
                            if 'committees' not in filer.metadata_json:
                                filer.metadata_json['committees'] = []
                            
                            if committee_name not in filer.metadata_json['committees']:
                                filer.metadata_json['committees'].append(committee_name)
                                self.logger.info(f"Added {member_name} to {committee_name}")
            
            session.commit()
            self.logger.info("Committee data saved successfully")
    
    def run(self):
        """Run full committee scraping and save."""
        
        self.logger.info("Starting committee scraping...")
        committee_data = self.scrape_all_committees()
        
        total_committees = len(committee_data.get('house', [])) + len(committee_data.get('senate', []))
        total_members = sum(len(c['members']) for c in committee_data.get('house', []) + committee_data.get('senate', []))
        
        self.logger.info(f"Scraped {total_committees} committees with {total_members} member assignments")
        
        self.save_committee_data(committee_data)
        
        return committee_data


def main():
    """Test committee scraper."""
    logging.basicConfig(level=logging.INFO)
    
    scraper = CommitteeScraper()
    result = scraper.run()
    
    print(f"\n✅ Committee Scraping Complete:")
    print(f"   House committees: {len(result.get('house', []))}")
    print(f"   Senate committees: {len(result.get('senate', []))}")
    
    for committee in result.get('house', [])[:3]:
        print(f"\n   {committee['name']}: {len(committee['members'])} members")


if __name__ == "__main__":
    main()

