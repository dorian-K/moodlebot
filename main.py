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

load_dotenv()
username = os.getenv("SSO_USERNAME") # username for rwth sso
password = os.getenv("SSO_PASSWORD") # password
mfa_name = os.getenv("SSO_TAN_NAME") # tan name, example: TOTP61....
mfa_secret = os.getenv("SSO_TAN_SECRET") # The secret you get for the mfa tan
discord_webhook = os.getenv("DISCORD_WEBHOOK_URL") # discord webhook for notification
discord_user_id = os.getenv("DISCORD_USER_ID") # the user that should be pinged

assert username, "SSO_USERNAME not set in .env"
assert password, "SSO_PASSWORD not set in .env"
assert mfa_name, "SSO_TAN_NAME not set in .env"
assert mfa_secret, "SSO_TAN_SECRET not set in .env"
assert discord_webhook, "DISCORD_WEBHOOK_URL not set in .env"
assert discord_user_id, "DISCORD_USER_ID not set in .env"

def make_mfa_code():
    global mfa_secret
    return pyotp.TOTP(mfa_secret).now()

def click(driver, element, expected_text=None):
    if expected_text:
        if isinstance(expected_text, list):
            assert any(text in element.text for text in expected_text), f"Expected text '{expected_text}' not found in element text '{element.text}'"
        else:
            assert expected_text in element.text, f"Expected text '{expected_text}' not found in element text '{element.text}'"
    driver.execute_script('arguments[0].click()', element)

def moodle_is_logged_in(driver):
    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "userinitials")))
        return True
    except:
        return False

def perform_until_login(driver, page_url, username, password, mfa_name):
    driver.get(page_url)
   
    if moodle_is_logged_in(driver):
        print("Session loaded from cache, login not required!")
        return
    print("Not logged in, proceeding to login...")
    
    click(driver, driver.find_element(By.XPATH, '//*[@id="usernavigation"]/div[3]/div/span/a'), ["Login", "Log in"])
   
    login_btn_xpath = '//*[@id="region-main"]/div/div[3]/div[2]/div/div[1]/a'
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, login_btn_xpath)))
    click(driver, driver.find_element(By.XPATH, login_btn_xpath), "Login via RWTH Single Sign-on")
   
    WebDriverWait(driver, 10).until(EC.url_contains("sso.rwth-aachen.de"))

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username"))).send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)
    click(driver, driver.find_element(By.ID, "login"), "Anmeldung")
    
    tan_selector_xpath = '//*[@id="fudis_selected_token_ids_input"]'
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, tan_selector_xpath)))
    select_element = Select(driver.find_element(By.XPATH, tan_selector_xpath))

    select_element.select_by_value(mfa_name)
    proceed_xpath = '//*[@id="fudiscr-form"]/button'
    proceed_elem = driver.find_element(By.XPATH, proceed_xpath)
    click(driver, proceed_elem, "Weiter")

    tan_xpath = '//*[@id="fudis_otp_input"]'
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, tan_xpath)))

    driver.find_element(By.XPATH, tan_xpath).send_keys(make_mfa_code())
    validate_xpath = '//*[@id="fudiscr-form"]/button[1]'
    validate_element = driver.find_element(By.XPATH, validate_xpath)
    click(driver, validate_element, "Überprüfen")

    WebDriverWait(driver, 10).until(EC.url_contains("moodle.rwth-aachen.de"))
    
def take_actions(driver, page_url):
    driver.get(page_url)

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "modtype_quiz")))

    data_elements = driver.find_elements(By.CLASS_NAME, "modtype_quiz")

    prev_elems = 0
    try:
        with open("prev_elems.data", "r") as f:
            prev_elems = int(f.read())
    except:
        pass

    if len(data_elements) is not prev_elems:
        print(data_elements)
        message = f"<@{discord_user_id}> New quiz available on moodle! Check it out at: " + page_url
        # try sending discord webhook for 3 trys
        for _ in range(3):
            try:
                import requests
                requests.post(discord_webhook, json={"content": message})
                break
            except:
                pass
        
        with open("prev_elems.data", "w") as f:
            f.write(str(len(data_elements)))

def teardown(driver):
    # by default cookies expire after the session closes, so we update the expiry to 3 days
    for cookie in driver.get_cookies():
        if "expiry" not in cookie and cookie['domain'].endswith("moodle.rwth-aachen.de"):
            cookie['expiry'] = 60 * 60 * 24 * 3 + int(time.time())
            driver.add_cookie(cookie)
            print("Updated expiry of cookie: ", cookie["name"])

    # Close the driver after the process
    driver.quit()

def lock():
    if os.path.exists("lock"):
        print("Script already running, exiting...")
        exit(0)
    else:
        with open("lock", "w") as f:
            f.write("1")

    def remove_lock():
        os.remove("lock")
    atexit.register(remove_lock)

if __name__ == "__main__":
    lock()

    options = webdriver.ChromeOptions()
    profile_path = "./selenium_profile"  # Path to save the profile data
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # options.add_argument('--headless')

    driver = webdriver.Chrome(options=options)
    page_url = "https://moodle.rwth-aachen.de/course/view.php?id=43600"
    try:
        perform_until_login(driver, page_url, username, password, mfa_name)
        take_actions(driver, page_url)
    except Exception as e:
        print("An error occurred: ", e)
    finally:
        teardown(driver)