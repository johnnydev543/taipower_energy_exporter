from json import decoder
import time
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client import start_http_server
import requests
import json
import re
import urllib

url = "https://data.taipower.com.tw/opendata01/apply/file/d006001/001.txt"

converter = {
    '核能':'nuclear',
    '燃煤':'coal',
    '汽電共生':'co_gen',
    '民營電廠-燃煤':'ipp_coal',
    '燃氣':'lng',
    '民營電廠-燃氣':'ipp_lng',
    '燃油':'oil',
    '輕油':'diesel',
    '水力':'hydro',
    '風力':'wind',
    '太陽能':'solar',
    '抽蓄發電':'pumping_gen',
    '抽蓄負載':'pumping_load',
    '地熱':'geothermal'
}

## remove () and included characters from the string
def stripper(s):
    s = re.sub('\(.+\)', '', s)
    return s

class TaipowerCollector(object):
    def collect(self):

        metrics = {}
        file = urllib.request.urlopen(url)

        # with open('001.txt') as f:
        #     decoded_line = f.readlines()
        for line in file:
            decoded_line = line.decode("utf-8")
        line_0 = json.loads(decoded_line)
        aaData = line_0['aaData']
        # print(aaData)

        pre_energy = ''
        now_energy = ''

        for data in aaData:

            ### data format
            # [
            #   ["ENERGY", "UNIT", "CAPACITY", "NET", "NOTE"],
            #   ["核能","核二#1","985.0","886.1","89.959%","燃料限制"],
            #   ...
            #   ...
            # ]
            ###
            energy = converter[data[0]]
            unit = stripper(data[1])
            cap = data[2]
            net = data[3]

            now_energy = energy

            if unit.find('小計') >= 0 :
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

            metrics[energy].add_metric([unit, 'cap'], cap)
            metrics[energy].add_metric([unit, 'net'], net)

        for m in metrics.values():
            yield m


if __name__ == "__main__":

    REGISTRY.register(TaipowerCollector())
    start_http_server(5000)
    while True:
        time.sleep(10)
