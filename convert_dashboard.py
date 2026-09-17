import json
from pathlib import Path

source = Path('taipower-watch.json')
destination = Path('provisioning/dashboards/taipower/taipower-watch-influx.json')

energy_queries = {
    '核能': ("nuclear", False),
    '燃煤': ("coal", False),
    '天然氣': ("lng", False),
    '太陽能': ("solar", False),
    '風力': ("wind", False),
    '汽電共生': ("co_gen", False),
    '燃油': ("fuel_oil", False),
    '輕油': ("diesel", False),
    '水力': ("hydro", False),
    '儲能/儲能負載': ("storage", False),
    '其它再生能源': ("other_renewable_energy", False),
}


def energy_query(energy_type, suffix=''):
    unit = 'unit' if not suffix else f"unit || '{suffix}' AS unit"
    return (
        f"SELECT time, {unit}, net_generation FROM taipower_energy "
        f"WHERE energy_type = '{energy_type}' AND $__timeFilter(time) ORDER BY time"
    )


dashboard = json.loads(source.read_text(encoding='utf-8'))
dashboard['id'] = None
dashboard['uid'] = 'taipower-watch-influx'
dashboard['title'] = 'Taipower Watch (InfluxDB)'
dashboard['version'] = 1
dashboard['tags'] = sorted(set(dashboard.get('tags', [])) | {'influxdb'})

influx = {'type': 'influxdb', 'uid': 'taipower-influxdb'}
for panel in dashboard['panels']:
    title = panel.get('title')
    if panel.get('targets'):
        panel['datasource'] = influx
    for target in panel.get('targets', []):
        target['datasource'] = influx
        target.pop('expr', None)
        target.pop('query', None)
        target.pop('exemplar', None)
        target.pop('interval', None)
        target.pop('editorMode', None)
        target.pop('range', None)
        target.pop('instant', None)
        target['editorMode'] = 'code'
        target['format'] = 'time_series'

        if title == '總發電量':
            if target['refId'] == 'A':
                target['rawSql'] = (
                    'SELECT time, total_net_generation AS "Total" FROM '
                    'taipower_energy_total WHERE $__timeFilter(time) ORDER BY time'
                )
            else:
                target['rawSql'] = (
                    'SELECT time + INTERVAL \'1 day\' AS time, '
                    'total_net_generation AS "Pre24H" FROM taipower_energy_total '
                    'WHERE time >= $__timeFrom - INTERVAL \'1 day\' '
                    'AND time <= $__timeTo - INTERVAL \'1 day\' ORDER BY time'
                )
        elif title == '即時總發電量':
            target['rawSql'] = (
                'SELECT time, total_net_generation AS "Total" FROM '
                'taipower_energy_total WHERE $__timeFilter(time) ORDER BY time'
            )
        elif title == '燃煤' and target['refId'] == 'B':
            target['rawSql'] = energy_query('ipp_coal', '-ipp')
        elif title == '天然氣' and target['refId'] == 'B':
            target['rawSql'] = energy_query('ipp_lng', '-ipp')
        elif title == '儲能/儲能負載' and target['refId'] == 'B':
            target['rawSql'] = energy_query('energy_storage_system_load', '負載')
        else:
            energy_type, _ = energy_queries[title]
            suffix = '儲能' if title == '儲能/儲能負載' else ''
            target['rawSql'] = energy_query(energy_type, suffix)

destination.write_text(
    json.dumps(dashboard, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
)
