from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from dotenv import load_dotenv
import pyotp
import os
import atexit
import time

# Add lock file to prevent multiple instances of the script running at the same time
if os.path.exists("lock"):
    print("Script already running, exiting...")
    exit(0)
else:
    with open("lock", "w") as f:
        f.write("1")

# Remove lock file after the script is done
def remove_lock():
    os.remove("lock")
atexit.register(remove_lock)

# Set up Chrome options with a specific user data directory
options = webdriver.ChromeOptions()
profile_path = "./selenium_profile"  # Path to save the profile data
options.add_argument(f"--user-data-dir={profile_path}")
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
# Optional: Headless mode, uncomment if needed
# options.add_argument('--headless')

load_dotenv()
username = os.getenv("SSO_USERNAME")
password = os.getenv("SSO_PASSWORD")
mfa_name = os.getenv("SSO_TAN_NAME")
mfa_secret = os.getenv("SSO_TAN_SECRET")
discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
discord_user_id = os.getenv("DISCORD_USER_ID")

assert username, "SSO_USERNAME not set in .env"
assert password, "SSO_PASSWORD not set in .env"
assert mfa_name, "SSO_TAN_NAME not set in .env"
assert mfa_secret, "SSO_TAN_SECRET not set in .env"
assert discord_webhook, "DISCORD_WEBHOOK_URL not set in .env"
assert discord_user_id, "DISCORD_USER_ID not set in .env"

def make_mfa_code():
    global mfa_secret
    return pyotp.TOTP(mfa_secret).now()

# Initialize the WebDriver with the user data directory
# ChromeDriverManager().install(), 
driver = webdriver.Chrome(options=options)

page_url = "https://moodle.rwth-aachen.de/course/view.php?id=43600"

# Visit login page if first time, else the session should be loaded from cache
driver.get(page_url)

def click(element, expected_text=None):
    global driver
    if expected_text:
        if isinstance(expected_text, list):
            assert any(text in element.text for text in expected_text), f"Expected text '{expected_text}' not found in element text '{element.text}'"
        else:
            assert expected_text in element.text, f"Expected text '{expected_text}' not found in element text '{element.text}'"
    driver.execute_script('arguments[0].click()', element)

# Check if already logged in by looking for an element unique to logged-in users
try:
    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "userinitials")))
    print("Session loaded from cache, login not required!")
except:
    print("Not logged in, proceeding to login...")
    # If not logged in, perform login actions
    click(driver.find_element(By.XPATH, '//*[@id="usernavigation"]/div[3]/div/span/a'), ["Login", "Log in"])
    # Wait for login page to load
    login_btn_xpath = '//*[@id="region-main"]/div/div[3]/div[2]/div/div[1]/a'
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, login_btn_xpath)))
    click(driver.find_element(By.XPATH, login_btn_xpath), "Login via RWTH Single Sign-on")
    
    # wait until url is on sso.rwth-aachen.de and then login
    WebDriverWait(driver, 10).until(EC.url_contains("sso.rwth-aachen.de"))
   
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username"))).send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)
    click(driver.find_element(By.ID, "login"), "Anmeldung")
    
    tan_selector_xpath = '//*[@id="fudis_selected_token_ids_input"]'
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, tan_selector_xpath)))
    select_element = Select(driver.find_element(By.XPATH, tan_selector_xpath))

    select_element.select_by_value(mfa_name)
    proceed_xpath = '//*[@id="fudiscr-form"]/button'
    proceed_elem = driver.find_element(By.XPATH, proceed_xpath)
    click(proceed_elem, "Weiter")

    tan_xpath = '//*[@id="fudis_otp_input"]'
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, tan_xpath)))
   
    driver.find_element(By.XPATH, tan_xpath).send_keys(make_mfa_code())
    validate_xpath = '//*[@id="fudiscr-form"]/button[1]'
    validate_element = driver.find_element(By.XPATH, validate_xpath)
    click(validate_element, "Überprüfen")

    WebDriverWait(driver, 10).until(EC.url_contains("moodle.rwth-aachen.de"))
    
    
# Now navigate to target page
driver.get(page_url)

WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "modtype_quiz")))

# Extract and print the data as required
data_elements = driver.find_elements(By.CLASS_NAME, "modtype_quiz")

# read prev number of elems from file
prev_elems = 0
try:
    with open("prev_elems.data", "r") as f:
        prev_elems = int(f.read())
except:
    pass

if len(data_elements) is not prev_elems:
    print(data_elements)
    message = f"<@{discord_user_id}> New quiz available on moodle! Check it out at: " + page_url + "!"
    # try sending discord webhook for 3 trys
    for i in range(3):
        try:
            import requests
            requests.post(discord_webhook, json={"content": message})
            break
        except:
            pass
    
    with open("prev_elems.data", "w") as f:
        f.write(str(len(data_elements)))

# by default cookies expire after the session closes, so we update the expiry to 3 days
for cookie in driver.get_cookies():
    if "expiry" not in cookie and cookie['domain'].endswith("moodle.rwth-aachen.de"):
        cookie['expiry'] = 60 * 60 * 24 * 3 + int(time.time())
        driver.add_cookie(cookie)
        print("Updated expiry of cookie: ", cookie["name"])

# Close the driver after the process
driver.quit()
