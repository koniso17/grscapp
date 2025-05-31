import requests
from bs4 import BeautifulSoup
import re
import time
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

base_url = "https://inasougo.com/course-a/course-a"
ajax_url = "https://inasougo.com/wp-admin/admin-ajax.php"
headers = {"User-Agent": "Mozilla/5.0"}

def get_cid_from_detail_page(detail_url):
    try:
        res = requests.get(detail_url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        scripts = soup.find_all("script", {"type": "text/javascript"})
        for script in scripts:
            if script.string:
                match = re.search(r"'cid'\s*:\s*(\d+)", script.string)
                if match:
                    return int(match.group(1))
        return None
    except Exception as e:
        return f"Error: {e}"

def get_course_dates_from_ajax(cid):
    payload = {"action": "get_course_calendar", "cid": cid}
    try:
        res = requests.post(ajax_url, data=payload)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        tables = soup.select("table.calendar")
        dates = []
        for table in tables:
            caption = table.find("caption")
            if not caption:
                continue
            year = caption.find("span", class_="cl_year").text.replace("年", "")
            month = caption.find("span", class_="cl_month").text.replace("月", "")
            for td in table.find_all("td"):
                if td.text.strip().endswith("●"):
                    day_span = td.find("span", class_="cl_day")
                    if day_span and day_span.text.isdigit():
                        day = day_span.text.zfill(2)
                        dates.append(f"{year}-{month.zfill(2)}-{day}")
        return sorted(list(set(dates)))
    except Exception as e:
        return [f"Error: {e}"]

# すべての講座情報取得
courses = []
page = 1
while True:
    url = base_url + "/" if page == 1 else f"{base_url}/page/{page}/"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        break
    soup = BeautifulSoup(response.text, "html.parser")
    course_list = soup.select("ul.course-a-list > li")
    if not course_list:
        break

    for li in course_list:
        title_tag = li.find("h3", class_="title")
        detail_link = li.find("a", class_="btn detail")
        time_text = place_text = ""
        for detail in li.find_all("li"):
            label = detail.find("label")
            if label:
                label_text = label.text.strip()
                value = detail.text.strip().replace(label_text, "")
                if label_text == "時間":
                    time_text = value
                elif label_text == "場所":
                    place_text = value

        detail_url = detail_link["href"] if detail_link else ""
        cid = get_cid_from_detail_page(detail_url) if detail_url else None
        dates = get_course_dates_from_ajax(cid) if isinstance(cid, int) else []

        courses.append({
            "cid": cid,
            "講座名": title_tag.text.strip() if title_tag else "",
            "時間": time_text,
            "場所": place_text,
            "詳細URL": detail_url,
            "実施日": ", ".join(dates)
        })

        time.sleep(1)

    page += 1

# Google Sheets に書き込み
df = pd.DataFrame(courses)

# 環境変数から認証ファイルを読み込む
with open("creds.json", "w") as f:
    f.write(os.environ["GOOGLE_SERVICE_ACCOUNT"])

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)

# スプレッドシートを開いて上書き
spreadsheet = client.open("講座一覧（自動更新）")
worksheet = spreadsheet.worksheet("シート1")
worksheet.clear()
worksheet.update([df.columns.tolist()] + df.values.tolist())