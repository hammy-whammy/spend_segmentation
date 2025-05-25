import time
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def build_company_url(company_id):
    """
    Construct the company details URL using the company ID.
    Example URL:
    https://datacvr.virk.dk/enhed/virksomhed/10150825?fritekst=10150825&sideIndex=0&size=10
    """
    return f"https://datacvr.virk.dk/enhed/virksomhed/{company_id}?fritekst={company_id}&sideIndex=0&size=10"

def extract_details(page):
    """
    Extracts details from the live DOM:
    - Wait for the company name (from an <h1> element with class "h2").
    - Force the accordion container (which holds additional info) to display.
    - Search for any <strong> element whose text includes "Branchekode"
      and retrieve its sibling's text.
    Returns a tuple: (company_name, activity_code, activity_description).
    """
    try:
        company_name = page.wait_for_selector("h1.h2", timeout=15000).inner_text().strip()
    except Exception as e:
        print("Error extracting company name:", e)
        company_name = "N/A"
    
    # Force the accordion container to display so its content is available.
    try:
        page.evaluate("document.querySelector('#accordion-udvidede-virksomhedsoplysninger-content').style.display = 'block';")
        time.sleep(1)
    except Exception as e:
        print("Error forcing accordion open:", e)
    
    try:
        # Search for any <strong> element that includes "Branchekode" and get its sibling's text.
        activity_details = page.evaluate("""
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
        print("Error extracting activity details via JS:", e)
        activity_code, activity_description = "N/A", "N/A"
    
    return company_name, activity_code, activity_description

def main():
    # Read the Excel file containing Danish company IDs.
    df_input = pd.read_excel("dk_cleaned.xlsx", sheet_name=0)
    if df_input.columns[0] != "DanishCompanyID":
        df_input.columns = ["DanishCompanyID"]
    
    total_count = len(df_input)
    df_output = pd.DataFrame(columns=["CompanyID", "CompanyName", "ActivityCode", "ActivityDescription"])
    
    with sync_playwright() as p:
        # Launch the browser in visible mode (headless=False).
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        # Create one persistent page that will be reused for all companies.
        page = context.new_page()
        
        for idx, row in df_input.iterrows():
            company_id = str(row.iloc[0]).strip()
            print(f"Processing company [{idx+1}/{total_count}]: {company_id}")
            company_url = build_company_url(company_id)
            print(f"Navigating to: {company_url}")
            
            try:
                page.goto(company_url, timeout=60000, wait_until="networkidle")
            except PlaywrightTimeoutError as e:
                print(f"Timeout navigating to {company_url}: {e}")
                df_output.loc[idx] = [company_id, "N/A", "N/A", "N/A"]
                continue
            except Exception as e:
                print(f"Error navigating to {company_url}: {e}")
                df_output.loc[idx] = [company_id, "N/A", "N/A", "N/A"]
                continue
            
            company_name, activity_code, activity_description = extract_details(page)
            print(f"Extracted details - Company: {company_name} | Code: {activity_code} | Desc: {activity_description}")
            df_output.loc[idx] = [company_id, company_name, activity_code, activity_description]
            
            time.sleep(1)
            
            # Write intermediate output every 10 iterations.
            if (idx + 1) % 10 == 0:
                df_output.to_excel("dk_cleaned_intermediate.xlsx", index=False)
                print(f"Intermediate file saved at iteration {idx+1}.")
        
        browser.close()
    
    df_output.to_excel("dk_cleaned_output_playwright.xlsx", index=False)
    print("Scraping complete. Output saved to dk_cleaned_output_playwright.xlsx.")

if __name__ == "__main__":
    main()