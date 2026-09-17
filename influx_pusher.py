import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import re
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path
from zoneinfo import ZoneInfo
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load configuration from config.json
with open('config.json', 'r') as f:
    config = json.load(f)

INFLUXDB_URL = config['INFLUXDB_URL']
INFLUXDB_TOKEN = config['INFLUXDB_TOKEN']
INFLUXDB_ORG = config['INFLUXDB_ORG']
INFLUXDB_BUCKET = config['INFLUXDB_BUCKET']
STATE_FILE = Path(config.get('STATE_FILE', '/state/last_source_timestamp'))
HTTP_TIMEOUT_SECONDS = config.get('HTTP_TIMEOUT_SECONDS', 20)
HTTP_RETRIES = config.get('HTTP_RETRIES', 3)
TAIPEI_TZ = ZoneInfo('Asia/Taipei')

url = "https://service.taipower.com.tw/data/opendata/apply/file/d006001/001.json"

http = requests.Session()
http.mount(
    'https://',
    HTTPAdapter(max_retries=Retry(
        total=HTTP_RETRIES,
        connect=HTTP_RETRIES,
        read=HTTP_RETRIES,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
    )),
)

converter = {
    '核能': 'nuclear',
    '燃煤': 'coal',
    '汽電共生': 'co_gen',
    '民營電廠-燃煤': 'ipp_coal',
    '燃氣': 'lng',
    '民營電廠-燃氣': 'ipp_lng',
    '燃油': 'oil',
    '輕油': 'diesel',
    '水力': 'hydro',
    '風力': 'wind',
    '太陽能': 'solar',
    '抽蓄發電': 'pumping_gen',
    '抽蓄負載': 'pumping_load',
    '地熱': 'geothermal',
    '其它再生能源': 'other_renewable_energy',
    '儲能': 'storage',
    '儲能負載': 'energy_storage_system_load',
    '燃料油': 'fuel_oil'
}

def stripper(s):
    s = re.sub(r'\s*\(.*\)', '', s)
    return s


def is_already_ingested(source_timestamp):
    """Avoid writing again while Taipower is still serving the same snapshot."""
    try:
        return STATE_FILE.read_text(encoding='utf-8').strip() == source_timestamp
    except FileNotFoundError:
        return False


def remember_ingested(source_timestamp):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix('.tmp')
    temporary.write_text(source_timestamp, encoding='utf-8')
    temporary.replace(STATE_FILE)

def collect_data():
    try:
        response = http.get(url, verify=False, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()

        raw_data = response.content.decode('utf-8-sig')
        data = json.loads(raw_data)
    except requests.Timeout:
        print('[', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ']', "TimeoutError")
        return None, None
    except requests.RequestException as e:
        print('[', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ']', e)
        return None, None
    except json.JSONDecodeError as e:
        print('[', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ']', f"JSON decode error: {e}")
        return None, None

    aaData = data['aaData']

    # Check if data is outdated
    source_timestamp = data["DateTime"]
    if is_already_ingested(source_timestamp):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Source data unchanged ({source_timestamp}); skipping write")
        return None, None

    # The upstream timestamp is Taiwan local time. Make it timezone-aware so
    # Grafana shows the source time correctly in a Taipei-timezone dashboard.
    txt_time = datetime.strptime(source_timestamp, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=TAIPEI_TZ)
    now_time = datetime.now(TAIPEI_TZ)
    time_delta = timedelta(minutes=30)
    txt_time_delta = now_time - txt_time
    if txt_time_delta > time_delta:
        print("Outdated data. Time elapsed: ", txt_time_delta)
        return None, None

    if not aaData:
        return None, None

    points = []
    total_cap = 0
    total_net = 0

    for item in aaData:
        data = item.copy()

        data["機組類型"] = BeautifulSoup(data["機組類型"], features="html.parser").get_text()
        data["機組類型"] = stripper(data["機組類型"])

        energy = ''
        if data["機組類型"] in converter.keys():
            energy = converter[data["機組類型"]]
        else:
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "New energy type: ", data["機組類型"])
            continue

        unit = stripper(data["機組名稱"])
        cap = data["裝置容量(MW)"]
        net = data["淨發電量(MW)"]

        if unit.find('小計') >= 0 or unit.find('離島其他') >= 0:
            continue
        if cap == '-' or cap == 'N/A':
            cap = 0
        if net == '-' or net == 'N/A':
            net = 0

        cap = float(cap)
        net = float(net)

        total_cap += cap
        total_net += net

        # Create InfluxDB point
        point = Point("taipower_energy") \
            .tag("energy_type", energy) \
            .tag("unit", unit) \
            .field("capacity", cap) \
            .field("net_generation", net) \
            .time(txt_time)

        points.append(point)

    # Add total points
    total_cap_point = Point("taipower_energy_total") \
        .field("total_capacity", total_cap) \
        .time(txt_time)
    total_net_point = Point("taipower_energy_total") \
        .field("total_net_generation", total_net) \
        .time(txt_time)

    points.extend([total_cap_point, total_net_point])

    return points, source_timestamp

def push_to_influxdb(points, source_timestamp):
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    try:
        write_api.write(bucket=INFLUXDB_BUCKET, record=points)
        remember_ingested(source_timestamp)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Data pushed to InfluxDB successfully")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error pushing to InfluxDB: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    while True:
        points, source_timestamp = collect_data()
        if points:
            push_to_influxdb(points, source_timestamp)
        time.sleep(600)  # Push every 10 minutes
