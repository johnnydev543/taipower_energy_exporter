# Taipower Energy Monitor

這個項目包含兩個主要腳本：

1. `script.py` - Prometheus exporter，用於從台灣電力公司獲取電力生產數據並暴露為 Prometheus 指標。
2. `influx_pusher.py` - 將數據推送到 InfluxDB3 的腳本。

## 設置

### 安裝依賴

```bash
pip install prometheus_client requests beautifulsoup4 influxdb-client
```

### 配置 InfluxDB

1. 複製 `config.json.example` 到 `config.json`：
   ```bash
   cp config.json.example config.json
   ```

2. 編輯 `config.json`，填入您的 InfluxDB3 配置：
   ```json
   {
       "INFLUXDB_URL": "https://your-influxdb-url:8086",
       "INFLUXDB_TOKEN": "your-actual-token",
       "INFLUXDB_ORG": "your-organization",
       "INFLUXDB_BUCKET": "your-bucket-name"
   }
   ```

注意：`config.json` 已添加到 `.gitignore` 中，不會被提交到版本控制。

### 運行腳本

- Prometheus exporter：
  ```bash
  python script.py
  ```

- InfluxDB pusher：
  ```bash
  python influx_pusher.py
  ```

## 數據結構

腳本收集台灣電力公司的電力生產數據，包括各種能源類型的容量和淨發電量。

數據會以以下格式推送到 InfluxDB：

- Measurement: `taipower_energy`
  - Tags: `energy_type`, `unit`
  - Fields: `capacity`, `net_generation`

- Measurement: `taipower_energy_total`
  - Fields: `total_capacity`, `total_net_generation`