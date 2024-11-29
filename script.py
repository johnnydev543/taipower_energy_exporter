import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client import start_http_server
import json
import re
import requests

url = "https://service.taipower.com.tw/data/opendata/apply/file/d006001/001.json"

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
    '儲能負載': 'storage_load'
}

## remove () and included characters from the string
def stripper(s):
    s = re.sub(r'\(.+\)', '', s)
    return s

class TaipowerCollector(object):
    def collect(self):

        metrics = {}
        aaData = []

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # check if returns 200 status code

            # use utf-8-sig decode to remove BOM
            raw_data = response.content.decode('utf-8-sig')

            data = json.loads(raw_data)
        except requests.Timeout:
            print('[', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ']', "TimeoutError")
            return
        except requests.RequestException as e:
            print('[', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ']', e)
            exit(1)
        except json.JSONDecodeError as e:
            print('[', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ']', f"JSON decode error: {e}")
            return

        aaData = data['aaData']

        # compare the txt time and the current time,
        # not using data if the txt file time exceeded 20 mins
        txt_time = datetime.strptime(data["DateTime"], "%Y-%m-%dT%H:%M:%S")
        now_time = datetime.now()
        time_delta = timedelta(minutes=20)
        txt_time_delta = now_time - txt_time
        if txt_time_delta > time_delta:
            print("Outdated data. Time elapsed: ", txt_time_delta)
            return

        pre_energy = ''
        now_energy = ''
        total_net = 0
        total_cap = 0

        if not aaData:
            return

        for data in aaData:

            ### data format
            # [
            #   ["ENERGY", "UNIT", "CAPACITY", "NET", "NOTE"],
            #   ["核能","核二#1","985.0","886.1","89.959%","燃料限制"],
            #   ...
            #   ...
            # ]
            ###
            data["機組類型"] = BeautifulSoup(data["機組類型"], features="html.parser").get_text()
            data[0] = stripper(data["機組類型"])
            if data["機組類型"] in converter.keys():
                energy = converter[data["機組類型"]]
            else:
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "New energy type: ", data["機組類型"])

            unit = stripper(data["機組名稱"])
            cap = data["裝置容量(MW)"]
            net = data["淨發電量(MW)"]

            now_energy = energy

            if unit.find('小計') >= 0:
                continue
            if unit.find('離島其他') >= 0:
                continue
            if cap == '-' or cap == 'N/A':
                cap = 0
            if net == '-' or net == 'N/A':
                net = 0

            # to prevent been overwrote by same energy(key)
            if pre_energy != now_energy:
                metrics[energy] = GaugeMetricFamily(
                    'taipower_energy_{0}'.format(energy),
                    'Taipower energy ' + energy + ' generation',
                    labels=['unit', 'gen'])

            pre_energy = now_energy

            total_cap = total_cap + float(cap)
            total_net = total_net + float(net)

            metrics[energy].add_metric([unit, 'cap'], cap)
            metrics[energy].add_metric([unit, 'net'], net)

        metrics['total_cap'] = GaugeMetricFamily(
            'taipower_energy_total_cap',
            'Taipower energy total generation capacity')
        metrics['total_net'] = GaugeMetricFamily(
            'taipower_energy_total_net',
            'Taipower energy total net generation')

        metrics['total_cap'].add_metric('', total_cap)
        metrics['total_net'].add_metric('', total_net)

        for m in metrics.values():
            yield m


if __name__ == "__main__":

    REGISTRY.register(TaipowerCollector())
    start_http_server(5000)
    while True:
        time.sleep(10)
