"""
Country-specific data scrapers for the JICAP Vendor Classification System
"""

import requests
import time
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple, List
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import re

from .config import Config
from .logger_config import get_logger

class CountryScraperBase(ABC):
    """Base class for country-specific scrapers"""
    
    def __init__(self, country_code: str):
        self.country_code = country_code.upper()
        self.logger = get_logger(f'scraper_{country_code.lower()}')
        
    @abstractmethod
    async def fetch_company_data(self, company_id: str) -> Dict[str, str]:
        """Fetch company data for the given company ID"""
        pass
    
    def _create_result_dict(self, company_name: str = "N/A", 
                           activity_code: str = "N/A", 
                           activity_description: str = "N/A") -> Dict[str, str]:
        """Create a standardized result dictionary"""
        return {
            'Company Name': company_name,
            'Local Activity Code': activity_code,
            'Local Activity Code Description': activity_description
        }

class FrenchScraper(CountryScraperBase):
    """Scraper for French companies using government API"""
    
    def __init__(self):
        super().__init__('FR')
        self.api_url = Config.FRENCH_API_URL
        
    async def fetch_company_data(self, company_id: str) -> Dict[str, str]:
        """Fetch French company data from government API"""
        try:
            url = self.api_url.format(siren=company_id)
            self.logger.debug(f"Fetching data for SIREN {company_id} from {url}")
            
            # Use asyncio to make the request non-blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.get(url, timeout=Config.DEFAULT_TIMEOUT)
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if 'results' in data and len(data['results']) > 0:
                    result = data['results'][0]
                    company_name = result.get('nom_complet', 'N/A')
                    activity_code = result.get('activite_principale', 'N/A')
                    activity_description = result.get('libelle_activite_principale', 'N/A')
                    
                    self.logger.debug(f"Successfully fetched data for SIREN {company_id}")
                    return self._create_result_dict(company_name, activity_code, activity_description)
                else:
                    self.logger.warning(f"No results found for SIREN {company_id}")
                    return self._create_result_dict()
            else:
                self.logger.error(f"API request failed for SIREN {company_id}: {response.status_code}")
                return self._create_result_dict()
                
        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout fetching data for SIREN {company_id}")
            return self._create_result_dict()
        except Exception as e:
            self.logger.error(f"Error fetching data for SIREN {company_id}: {str(e)}")
            return self._create_result_dict()

class BelgianScraper(CountryScraperBase):
    """Scraper for Belgian companies using web scraping"""
    
    def __init__(self):
        super().__init__('BE')
        self.base_url = Config.BELGIAN_BASE_URL
        
    async def fetch_company_data(self, company_id: str) -> Dict[str, str]:
        """Fetch Belgian company data using web scraping"""
        try:
            url = f"{self.base_url}?nummer={company_id}&actionLu=Search"
            self.logger.debug(f"Fetching Belgian data for company {company_id}")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=Config.PLAYWRIGHT_SETTINGS['headless'])
                context = await browser.new_context()
                page = await context.new_page()
                
                try:
                    await page.goto(url, timeout=Config.PLAYWRIGHT_SETTINGS['timeout'], 
                                   wait_until=Config.PLAYWRIGHT_SETTINGS['wait_until'])
                    
                    # Extract company details
                    company_name, tax_code, description = await self._extract_belgian_details(page)
                    
                    await browser.close()
                    
                    self.logger.debug(f"Successfully scraped Belgian data for company {company_id}")
                    return self._create_result_dict(company_name, tax_code, description)
                    
                except PlaywrightTimeoutError:
                    self.logger.error(f"Timeout scraping Belgian data for company {company_id}")
                    await browser.close()
                    return self._create_result_dict()
                    
        except Exception as e:
            self.logger.error(f"Error scraping Belgian data for company {company_id}: {str(e)}")
            return self._create_result_dict()
    
    async def _extract_belgian_details(self, page) -> Tuple[str, str, str]:
        """Extract details from Belgian company page"""
        company_name = "N/A"
        tax_code = "N/A"
        description = "N/A"
        
        try:
            # Extract company name
            name_element = await page.wait_for_selector("//tr[td[contains(text(), 'Name:')]]/td[2]", timeout=5000)
            if name_element:
                raw_text = await name_element.inner_text()
                company_name = raw_text.strip().split("\n")[0].replace('"', '').strip()
        except Exception as e:
            self.logger.debug(f"Error extracting company name: {e}")
        
        # Try to extract NSSO2025 data first
        extracted = False
        try:
            nss_element = await page.wait_for_selector("//td[contains(., 'NSSO2025') and contains(@class, 'QL')]", timeout=10000)
            if nss_element:
                nss_text = await nss_element.inner_text()
                nss_text = " ".join(nss_text.split())
                pattern = r"NSSO2025\s+([\d\.]+)\s*-\s*(.*?)(?:\s+Since|$)"
                match = re.search(pattern, nss_text)
                if match:
                    tax_code = match.group(1).strip()
                    description = match.group(2).strip()
                    extracted = True
        except Exception as e:
            self.logger.debug(f"NSSO2025 element not found: {e}")
        
        # If NSSO2025 not found, try VAT2008
        if not extracted:
            try:
                vat_element = await page.wait_for_selector("//td[(contains(., 'VAT2008') or contains(., 'VAT 2008')) and contains(@class, 'QL')]", timeout=10000)
                if vat_element:
                    vat_text = await vat_element.inner_text()
                    vat_text = " ".join(vat_text.split())
                    pattern = r"VAT ?2008\s+([\d\.]+)\s*-\s*(.*?)(?:\s+Since|$)"
                    match = re.search(pattern, vat_text)
                    if match:
                        tax_code = match.group(1).strip()
                        description = match.group(2).strip()
            except Exception as e:
                self.logger.debug(f"VAT2008 element not found: {e}")
        
        return company_name, tax_code, description

class DanishScraper(CountryScraperBase):
    """Scraper for Danish companies using web scraping"""
    
    def __init__(self):
        super().__init__('DK')
        self.base_url = Config.DANISH_BASE_URL
        
    async def fetch_company_data(self, company_id: str) -> Dict[str, str]:
        """Fetch Danish company data using web scraping"""
        try:
            url = self.base_url.format(company_id=company_id)
            self.logger.debug(f"Fetching Danish data for company {company_id}")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=Config.PLAYWRIGHT_SETTINGS['headless'])
                context = await browser.new_context()
                page = await context.new_page()
                
                try:
                    await page.goto(url, timeout=Config.PLAYWRIGHT_SETTINGS['timeout'],
                                   wait_until=Config.PLAYWRIGHT_SETTINGS['wait_until'])
                    
                    # Extract company details
                    company_name, activity_code, activity_description = await self._extract_danish_details(page)
                    
                    await browser.close()
                    
                    self.logger.debug(f"Successfully scraped Danish data for company {company_id}")
                    return self._create_result_dict(company_name, activity_code, activity_description)
                    
                except PlaywrightTimeoutError:
                    self.logger.error(f"Timeout scraping Danish data for company {company_id}")
                    await browser.close()
                    return self._create_result_dict()
                    
        except Exception as e:
            self.logger.error(f"Error scraping Danish data for company {company_id}: {str(e)}")
            return self._create_result_dict()
    
    async def _extract_danish_details(self, page) -> Tuple[str, str, str]:
        """Extract details from Danish company page"""
        try:
            # Extract company name
            company_name_element = await page.wait_for_selector("h1.h2", timeout=15000)
            company_name = await company_name_element.inner_text() if company_name_element else "N/A"
            company_name = company_name.strip()
        except Exception as e:
            self.logger.debug(f"Error extracting company name: {e}")
            company_name = "N/A"
        
        # Force accordion to display
        try:
            await page.evaluate("document.querySelector('#accordion-udvidede-virksomhedsoplysninger-content').style.display = 'block';")
            await asyncio.sleep(1)
        except Exception as e:
            self.logger.debug(f"Error forcing accordion open: {e}")
        
        try:
            # Extract activity details using JavaScript
            activity_details = await page.evaluate("""
                () => {
                    const elems = Array.from(document.querySelectorAll("strong"));
                    const brancheElem = elems.find(el => el.textContent.includes("Branchekode"));
                    if (brancheElem) {
                        const sibling = brancheElem.parentElement.nextElementSibling;
                        return sibling ? sibling.textContent.trim() : null;
                    }
                    return null;
                }
            """)
            
            if activity_details:
                parts = activity_details.split(" ", 1)
                if len(parts) == 2:
                    activity_code = parts[0].strip()
                    activity_description = parts[1].strip()
                else:
                    activity_code, activity_description = "N/A", "N/A"
            else:
                activity_code, activity_description = "N/A", "N/A"
                
        except Exception as e:
            self.logger.debug(f"Error extracting activity details: {e}")
            activity_code, activity_description = "N/A", "N/A"
        
        return company_name, activity_code, activity_description

class CountryScraperFactory:
    """Factory class to create country-specific scrapers"""
    
    _scrapers = {
        'FR': FrenchScraper,
        'BE': BelgianScraper,
        'DK': DanishScraper
    }
    
    @classmethod
    def create_scraper(cls, country_code: str) -> CountryScraperBase:
        """Create a scraper for the specified country"""
        country_code = country_code.upper()
        
        if country_code not in cls._scrapers:
            raise ValueError(f"Unsupported country: {country_code}")
        
        return cls._scrapers[country_code]()
    
    @classmethod
    def get_supported_countries(cls) -> List[str]:
        """Get list of supported country codes"""
        return list(cls._scrapers.keys())
    
    @classmethod
    def is_supported(cls, country_code: str) -> bool:
        """Check if a country is supported"""
        return country_code.upper() in cls._scrapers
