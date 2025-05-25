import time
import pandas as pd
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def build_company_url(company_id):
    """
    Construct the company details URL using the company ID.
    Example URL:
    https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html?nummer=201105843&actionLu=Search
    """
    return f"https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html?nummer={company_id}&actionLu=Search"

def extract_details(page):
    """
    Extracts details from the rendered page:
    1. Extracts the company name from the table row that contains 'Name:'.
    2. Tries to extract NSSO2025 data first. If not found, tries VAT2008.
    Returns a tuple: (company_name, tax_code, description)
    """
    company_name = "N/A"
    tax_code = "N/A"
    description = "N/A"

    # 1) Extract the Company Name
    try:
        # Wait for the cell containing 'Name:' and extract its corresponding value
        name_td = page.wait_for_selector("//tr[td[contains(text(), 'Name:')]]/td[2]", timeout=5000)
        # Assume the first line contains the company name; remove any quotes.
        raw_text = name_td.inner_text().strip()
        company_name = raw_text.split("\n")[0].replace('"', '').strip()
    except Exception as e:
        print(f"Error extracting company name: {e}")
    
    extracted = False

    # 2) Try to extract NSSO2025 data first
    try:
        nss_td = page.wait_for_selector("//td[contains(., 'NSSO2025') and contains(@class, 'QL')]", timeout=10000)
        nss_text = nss_td.inner_text().strip()
        nss_text = " ".join(nss_text.split())
        # Example: "NSSO2025 84.130 - Regulation of ..."
        pattern = r"NSSO2025\s+([\d\.]+)\s*-\s*(.*?)(?:\s+Since|$)"
        match = re.search(pattern, nss_text)
        if match:
            tax_code = match.group(1).strip()
            description = match.group(2).strip()
            extracted = True
        else:
            print(f"NSSO2025 regex did not match: {nss_text}")
    except Exception as e:
        print(f"NSSO2025 element not found: {e}")
    
    # 3) If NSSO2025 not found, try VAT2008
    if not extracted:
        try:
            vat_td = page.wait_for_selector("//td[(contains(., 'VAT2008') or contains(., 'VAT 2008')) and contains(@class, 'QL')]", timeout=10000)
            vat_text = vat_td.inner_text().strip()
            vat_text = " ".join(vat_text.split())
            # Example: "VAT2008 49.100 - Passenger rail transport, excluding urban and suburban"
            pattern = r"VAT ?2008\s+([\d\.]+)\s*-\s*(.*?)(?:\s+Since|$)"
            match = re.search(pattern, vat_text)
            if match:
                tax_code = match.group(1).strip()
                description = match.group(2).strip()
                extracted = True
            else:
                print(f"VAT2008 regex did not match: {vat_text}")
        except Exception as e:
            print(f"VAT2008 element not found: {e}")

    return company_name, tax_code, description

def main():
    INPUT_FILE = 'unique_belgian_vendors_sirens.xlsx'
    OUTPUT_FILE = 'output.xlsx'
    
    # Read input Excel file. Assume it has a column named 'Company' with the company IDs.
    df = pd.read_excel(INPUT_FILE)
    siren_codes = df['Company'].tolist()
    
    # Initialize a DataFrame for results.
    results_df = pd.DataFrame(columns=['Company Name', 'Company Number', 'Tax Code', 'Description'])
    
    consecutive_na_count = 0
    MAX_CONSECUTIVE_NA = 5
    
    with sync_playwright() as p:
        # Launch the browser (headless can be True; change to False for debugging).
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        for i, code in enumerate(siren_codes, 1):
            url = build_company_url(code)
            print(f"Processing company [{i}/{len(siren_codes)}]: {code}")
            print(f"Navigating to: {url}")
            
            try:
                page.goto(url, timeout=30000, wait_until="networkidle")
            except PlaywrightTimeoutError as e:
                print(f"Timeout navigating to {url}: {e}")
                results_df.loc[i-1] = [ "N/A", code, "N/A", "N/A" ]
                continue
            except Exception as e:
                print(f"Error navigating to {url}: {e}")
                results_df.loc[i-1] = [ "N/A", code, "N/A", "N/A" ]
                continue
            
            company_name, tax_code, description = extract_details(page)
            print(f"Extracted details - Company: {company_name} | Tax Code: {tax_code} | Description: {description}")
            results_df.loc[i-1] = [company_name, code, tax_code, description]
            
            # Count consecutive N/A results.
            if company_name == "N/A" and tax_code == "N/A" and description == "N/A":
                consecutive_na_count += 1
                print(f"Warning: {consecutive_na_count} consecutive N/A results")
                if consecutive_na_count >= MAX_CONSECUTIVE_NA:
                    print("Too many consecutive N/A results. The website might be blocking requests.")
                    print(f"Saving {i-1} processed results and stopping...")
                    break
            else:
                consecutive_na_count = 0
            
            # Save intermediate results every 10 iterations.
            if i % 10 == 0:
                intermediate_file = f'intermediate_results_{i}.xlsx'
                results_df.to_excel(intermediate_file, index=False)
                print(f"Saved intermediate results to {intermediate_file}")
            
            time.sleep(1)
        
        browser.close()
    
    results_df.to_excel(OUTPUT_FILE, index=False)
    print(f"Final results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()