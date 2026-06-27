"""
天气预警脚本 - Open-Meteo 免费API
经纬度: 23.17, 113.31 (广州)
每天7点执行，判断通勤时段(8-9点/18-21点)是否需要带雨伞或遮阳伞
"""

import os
import smtplib
import ssl
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText

import requests

# ========== 配置区 ==========
LAT = 23.17
LON = 113.31
# QQ邮箱配置
QQ_EMAIL = "821116234@qq.com"  # ← 改成你的QQ邮箱
QQ_AUTH_CODE = os.environ.get('SMTP')  # ← 改成QQ邮箱授权码（非密码）
RECEIVER_EMAILS = [
    "821116234@qq.com",
    "1250423696@qq.com",
]  # ← 接收邮件的邮箱列表

# 阈值配置
PRECIP_PROB_THRESHOLD = 50  # 降水概率 %
UV_THRESHOLD = 6  # UV指数，≥6 需遮阳伞
HUMIDITY_THRESHOLD = 90  # 湿度 %
CLOUD_THRESHOLD = 80  # 云量 %
WIND_GUST_THRESHOLD = 40  # 阵风 km/h，风太大伞没用

# 通勤时段（24小时制）
MORNING_START, MORNING_END = 8, 9  # 出门：8~9点
EVENING_START, EVENING_END = 18, 21  # 回家：18~21点
# ============================


def fetch_weather(
    morning_start=MORNING_START,
    morning_end=MORNING_END,
    evening_start=EVENING_START,
    evening_end=EVENING_END,
):
    """从 Open-Meteo 获取今日逐小时+全天天气（免费，无需API Key）"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": [
            "temperature_2m",
            "precipitation_probability",
            "precipitation",
            "weathercode",
            "relative_humidity_2m",
            "cloud_cover",
            "uv_index",
            "wind_speed_10m",
            "wind_gusts_10m",
        ],
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "precipitation_sum",
            "weathercode",
            "wind_speed_10m_max",
            "uv_index_max",
            "sunrise",
            "sunset",
        ],
        "timezone": "Asia/Shanghai",
        "forecast_days": 2,  # 取2天覆盖跨夜时段
    }
    resp = requests.get(
        url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
    )
    resp.raise_for_status()
    data = resp.json()

    # ---------- 解析逐小时数据 ----------
    hourly = data["hourly"]
    times = hourly["time"]

    def extract_hourly_range(start_h, end_h):
        """提取某个时段内的逐小时数据"""
        records = []
        for i, t in enumerate(times):
            hour = int(t.split("T")[1].split(":")[0])
            date_str = t.split("T")[0]
            # 今天日期
            today = data["daily"]["time"][0]
            if date_str == today and start_h <= hour <= end_h:
                records.append(
                    {
                        "time": t,
                        "hour": hour,
                        "temp": hourly["temperature_2m"][i],
                        "precip_prob": hourly["precipitation_probability"][i],
                        "precip": hourly["precipitation"][i],
                        "weathercode": hourly["weathercode"][i],
                        "humidity": hourly["relative_humidity_2m"][i],
                        "cloud_cover": hourly["cloud_cover"][i],
                        "uv_index": hourly["uv_index"][i],
                        "wind_speed": hourly["wind_speed_10m"][i],
                        "wind_gust": hourly["wind_gusts_10m"][i],
                    }
                )
        return records

    morning_hours = extract_hourly_range(morning_start, morning_end)
    evening_hours = extract_hourly_range(evening_start, evening_end)

    # ---------- 解析全天数据 ----------
    daily = data["daily"]
    daily_data = {
        "date": daily["time"][0],
        "temp_max": daily["temperature_2m_max"][0],
        "temp_min": daily["temperature_2m_min"][0],
        "precip_prob_max": daily["precipitation_probability_max"][0],
        "precip_sum": daily["precipitation_sum"][0],
        "weathercode": daily["weathercode"][0],
        "wind_max": daily["wind_speed_10m_max"][0],
        "uv_index_max": daily["uv_index_max"][0],
        "sunrise": daily["sunrise"][0].split("T")[1],
        "sunset": daily["sunset"][0].split("T")[1],
    }

    return daily_data, morning_hours, evening_hours


def weathercode_desc(code):
    """将 WMO 天气代码转为中文描述"""
    codes = {
        0: "晴天",
        1: "大部晴",
        2: "多云",
        3: "阴天",
        45: "雾",
        48: "雾凇",
        51: "小毛毛雨",
        53: "中毛毛雨",
        55: "大毛毛雨",
        56: "冻毛毛雨",
        57: "冻毛毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        66: "冻雨",
        67: "冻雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        77: "雪粒",
        80: "阵雨",
        81: "中阵雨",
        82: "大阵雨",
        85: "小阵雪",
        86: "大阵雪",
        95: "雷暴",
        96: "雷暴+冰雹",
        99: "雷暴+冰雹",
    }
    return codes.get(code, f"未知({code})")


def _build_hourly_table(hours, label):
    """构建某个通勤时段的逐小时HTML表格"""
    if not hours:
        return f'<div style="text-align: center; padding: 22px; color: #6B7477; font-size: 14px; background-color: #F7FAF8; border: 1px solid #DFE8E3; border-radius: 8px;">暂无{label}数据</div>'

    rows = ""
    for i, h in enumerate(hours):
        precip_prob = h['precip_prob']
        uv = h['uv_index']
        precip_color = "#B74235" if precip_prob >= 50 else "#536268"
        precip_bg = "#FFF1EE" if precip_prob >= 50 else "#F7FAF8"
        precip_fw = "700" if precip_prob >= 50 else "500"
        uv_color = "#A86514" if uv >= UV_THRESHOLD else "#536268"
        uv_fw = "700" if uv >= UV_THRESHOLD else "500"
        gust_color = (
            "#A86514" if h['wind_gust'] >= WIND_GUST_THRESHOLD else "#536268"
        )
        row_bg = "#FFFFFF" if i % 2 == 0 else "#FAFCFB"
        rows += f"""<tr style="background-color: {row_bg};">
              <td style="padding: 12px 10px; text-align: center; border-bottom: 1px solid #E8EFEB; font-weight: 700; color: #1F2A2E; white-space: nowrap;">{h['hour']}:00</td>
              <td style="padding: 12px 10px; text-align: center; border-bottom: 1px solid #E8EFEB; color: #263237; font-weight: 600;">{weathercode_desc(h['weathercode'])}<br><span style="color: #6B7477; font-size: 12px; font-weight: 500;">{h['temp']}°C</span></td>
              <td style="padding: 12px 10px; text-align: center; border-bottom: 1px solid #E8EFEB;"><span style="display: inline-block; padding: 3px 6px; border-radius: 6px; background-color: {precip_bg}; color: {precip_color}; font-weight: {precip_fw};">{precip_prob}%</span><br><span style="color: #7B8588; font-size: 12px; font-weight: 500;">{h['precip']}mm</span></td>
              <td style="padding: 12px 10px; text-align: center; border-bottom: 1px solid #E8EFEB; color: {uv_color}; font-weight: {uv_fw};">{uv}</td>
              <td style="padding: 12px 10px; text-align: center; border-bottom: 1px solid #E8EFEB; color: {gust_color}; font-size: 13px; font-weight: 600;">{h['wind_gust']}<span style="font-size:11px; color: #7B8588;">km/h</span></td>
            </tr>"""

    return f"""<table width="100%" border="0" cellpadding="0" cellspacing="0" style="border-collapse: collapse; font-size: 14px; background-color: #FFFFFF; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
          <thead>
            <tr style="background-color: #EEF5F1;">
              <th style="padding: 12px 10px; font-weight: 700; color: #536268; text-align: center; border-bottom: 1px solid #D8E5DE;">时间</th>
              <th style="padding: 12px 10px; font-weight: 700; color: #536268; text-align: center; border-bottom: 1px solid #D8E5DE;">天气</th>
              <th style="padding: 12px 10px; font-weight: 700; color: #536268; text-align: center; border-bottom: 1px solid #D8E5DE;">降水</th>
              <th style="padding: 12px 10px; font-weight: 700; color: #536268; text-align: center; border-bottom: 1px solid #D8E5DE;">UV</th>
              <th style="padding: 12px 10px; font-weight: 700; color: #536268; text-align: center; border-bottom: 1px solid #D8E5DE;">阵风</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""


def send_email(
    daily_data,
    morning_hours,
    evening_hours,
    decisions,
    morning_start=MORNING_START,
    morning_end=MORNING_END,
    evening_start=EVENING_START,
    evening_end=EVENING_END,
    is_workday=True,
):
    """通过QQ邮箱发送美化天气邮件"""
    date_str = daily_data["date"]

    # --- 时段标签 ---
    if is_workday:
        morning_label = "🌅 早间通勤"
        evening_label = "🌇 晚间通勤"
    else:
        morning_label = "☀️ 白天出门"
        evening_label = "🌙 晚间出门"

    # --- 逻辑关联与邮件标题 ---
    has_rain = decisions["need_umbrella"]
    has_wind = decisions["wind_warning"]
    has_sun = decisions["need_sun_umbrella"]

    alert_parts = []
    if has_rain:
        alert_parts.append("🧥穿雨衣" if has_wind else "☔带雨伞")
    elif has_wind:
        alert_parts.append("💨防风外套")

    if has_sun and not has_rain:
        alert_parts.append("🧴涂防晒" if has_wind else "⛱️带遮阳伞")

    subject = f"🌤️ 天气提醒 {date_str}" + (
        f" — {' / '.join(alert_parts)}" if alert_parts else " — 今日爽朗"
    )

    if alert_parts:
        main_status = " / ".join(alert_parts)
        status_note = "今天出门前请优先处理这些事项。"
    else:
        main_status = "今日爽朗"
        status_note = "通勤时段暂无明显降水、防晒或大风风险。"

    def recommendation_card(kicker, title, detail, bg, border, accent, text):
        return f"""<table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 10px; border-collapse: separate; border-spacing: 0;">
          <tr>
            <td style="background-color: {bg}; border: 1px solid {border}; border-left: 4px solid {accent}; border-radius: 8px; padding: 13px 15px;">
              <span style="display: block; color: {accent}; font-size: 11px; font-weight: 800; letter-spacing: 0.6px; text-transform: uppercase; margin-bottom: 4px;">{kicker}</span>
              <strong style="display: block; color: #1F2A2E; font-size: 15px; line-height: 1.45; margin-bottom: 3px;">{title}</strong>
              <span style="display: block; color: {text}; font-size: 13px; line-height: 1.65;">{detail}</span>
            </td>
          </tr>
        </table>"""

    def metric_cell(label, value, helper, value_color="#1F2A2E"):
        return f"""<td width="48%" valign="top" style="background-color: #F7FAF8; border: 1px solid #DFE8E3; border-radius: 8px; padding: 14px 15px;">
          <span style="display: block; color: #6B7477; font-size: 12px; line-height: 1.3; margin-bottom: 6px;">{label}</span>
          <strong style="display: block; color: {value_color}; font-size: 18px; line-height: 1.2; font-weight: 800; white-space: nowrap;">{value}</strong>
          <span style="display: block; color: #7B8588; font-size: 12px; line-height: 1.45; margin-top: 5px;">{helper}</span>
        </td>"""

    # --- 建议模块 ---
    recs_html = ""

    # 1. 降水建议
    if has_rain:
        if has_wind:
            recs_html += recommendation_card(
                "rain + wind",
                "风雨同时出现，优先穿防水外套",
                f'{decisions["umbrella_reason"]}。阵风达 {decisions["max_gust"]}km/h，雨伞可能不太好用。',
                "#FFF3EF",
                "#F1D1C8",
                "#B74235",
                "#894239",
            )
        else:
            recs_html += recommendation_card(
                "rain",
                "带伞出门更稳妥",
                decisions["umbrella_reason"],
                "#FFF3EF",
                "#F1D1C8",
                "#B74235",
                "#894239",
            )

    # 2. 纯大风建议
    if has_wind and not has_rain:
        recs_html += recommendation_card(
            "wind",
            f'阵风较大，峰值 {decisions["max_gust"]}km/h',
            "出行建议穿防风外套，路上注意高空坠物和骑行安全。",
            "#FFF8E8",
            "#EAD8AF",
            "#A86514",
            "#7A541F",
        )

    # 3. 防晒建议
    if has_sun:
        if has_wind:
            recs_html += recommendation_card(
                "uv",
                "紫外线偏高，建议涂防晒或戴帽子",
                f'UV 达 {decisions["max_uv"]}。今天风偏大，遮阳伞不一定方便。',
                "#FFF8E8",
                "#EAD8AF",
                "#A86514",
                "#7A541F",
            )
        else:
            recs_html += recommendation_card(
                "uv",
                f'需要防晒，UV {decisions["max_uv"]}',
                "紫外线指数较高，出门建议带遮阳伞或涂抹防晒霜。",
                "#FFF8E8",
                "#EAD8AF",
                "#A86514",
                "#7A541F",
            )

    if not recs_html:
        recs_html = recommendation_card(
            "clear",
            "天气怡人，轻装出门",
            "今日无明显降水、防晒或大风提醒，按日常装备出门即可。",
            "#F2F8F3",
            "#D5E7D8",
            "#4F7F5C",
            "#4F7458",
        )

    precip_value_color = (
        "#B74235" if daily_data["precip_prob_max"] >= 50 else "#1F2A2E"
    )
    uv_value_color = (
        "#A86514" if daily_data["uv_index_max"] >= UV_THRESHOLD else "#1F2A2E"
    )

    # --- 核心 HTML 结构 ---
    body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>天气提醒 {date_str}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #EAF1EE; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: #1F2A2E;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #EAF1EE;">
    <tr>
      <td align="center" style="padding: 0;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 32px auto; border-collapse: separate; border-spacing: 0; background-color: #FFFFFF; border: 1px solid #D8E5DE; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);">
          <tr>
            <td style="padding: 32px 24px 24px; background-color: #0F343B;">
              <span style="display: inline-block; padding: 5px 9px; border-radius: 6px; background-color: #DCECE6; color: #0F343B; font-size: 12px; font-weight: 800;">{date_str}</span>
              <h1 style="margin: 16px 0 6px; color: #FFFFFF; font-size: 30px; line-height: 1.18; font-weight: 850; letter-spacing: 0;">{main_status}</h1>
              <p style="margin: 0; color: #BFD5D0; font-size: 14px; line-height: 1.65;">{status_note}<br>日出 {daily_data['sunrise']} · 日落 {daily_data['sunset']} · 坐标 {LAT}, {LON}</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 32px 24px 8px;">
              <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0 12px;">
                <tr>
                  {metric_cell("当前天气", weathercode_desc(daily_data['weathercode']), "全天概览", "#1F2A2E")}
                  <td width="4%"></td>
                  {metric_cell("气温区间", f"{daily_data['temp_min']}°C～{daily_data['temp_max']}°C", "最低 / 最高", "#1F2A2E")}
                </tr>
                <tr>
                  {metric_cell("最高降水", f"{daily_data['precip_prob_max']}%", f"累计 {daily_data['precip_sum']}mm", precip_value_color)}
                  <td width="4%"></td>
                  {metric_cell("UV / 阵风", f"{daily_data['uv_index_max']} / {daily_data['wind_max']}", "指数 / km/h", uv_value_color)}
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding: 4px 24px 10px;">
              <h2 style="margin: 0 0 12px; color: #1F2A2E; font-size: 16px; line-height: 1.3; font-weight: 850;">今日建议</h2>
              {recs_html}
            </td>
          </tr>
          <tr>
            <td style="padding: 8px 24px 18px;">
              <h2 style="margin: 0 0 10px; color: #1F2A2E; font-size: 16px; line-height: 1.3; font-weight: 850;">{morning_label} <span style="color: #6B7477; font-size: 12px; font-weight: 650;">{morning_start}:00-{morning_end}:00</span></h2>
              <div style="border: 1px solid #D8E5DE; border-radius: 8px; overflow: hidden; margin-bottom: 22px;">
                {_build_hourly_table(morning_hours, morning_label)}
              </div>
              <h2 style="margin: 0 0 10px; color: #1F2A2E; font-size: 16px; line-height: 1.3; font-weight: 850;">{evening_label} <span style="color: #6B7477; font-size: 12px; font-weight: 650;">{evening_start}:00-{evening_end}:00</span></h2>
              <div style="border: 1px solid #D8E5DE; border-radius: 8px; overflow: hidden;">
                {_build_hourly_table(evening_hours, evening_label)}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding: 17px 24px; background-color: #F2F7F4; border-top: 1px solid #D8E5DE; text-align: center;">
              <p style="margin: 0; color: #6B7477; font-size: 12px; line-height: 1.6;">本邮件由系统自动生成 · 数据源 Open-Meteo</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = QQ_EMAIL
    msg["To"] = ", ".join(RECEIVER_EMAILS)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.qq.com", 465, context=context) as server:
            server.login(QQ_EMAIL, QQ_AUTH_CODE)
            server.sendmail(QQ_EMAIL, RECEIVER_EMAILS, msg.as_string())
    except (OSError, smtplib.SMTPException) as e:
        print(f"⚠️ 邮件发送失败: {e}")
        return False

    print(f"✅ 邮件已发送至 {', '.join(RECEIVER_EMAILS)}")
    return True


def _analyze_hours(hours):
    """分析某时段的逐小时数据，返回是否需要雨伞及原因"""
    for h in hours:
        if (
            h["precip_prob"] is not None
            and h["precip_prob"] >= PRECIP_PROB_THRESHOLD
        ):
            return True, f"{h['hour']}点降水概率{h['precip_prob']}%"
    for h in hours:
        if h["precip"] is not None and h["precip"] >= 1:
            return True, f"{h['hour']}点预计降水{h['precip']}mm"
    for h in hours:
        if (
            h["humidity"] is not None
            and h["cloud_cover"] is not None
            and h["humidity"] >= HUMIDITY_THRESHOLD
            and h["cloud_cover"] >= CLOUD_THRESHOLD
        ):
            return (
                True,
                f"{h['hour']}点湿度{h['humidity']}%+云量{h['cloud_cover']}%",
            )
    RAIN_CODES = {95, 96, 99}
    for h in hours:
        if h["weathercode"] in RAIN_CODES:
            return True, f"{h['hour']}点{weathercode_desc(h['weathercode'])}"
    return False, ""


def is_workday():
    """判断今天是否为工作日（含调休），使用 timor.tech 免费API
    type: 0=工作日, 1=周末休息, 2=节假日休息, 3=调休补班
    返回 True 表示需要上班，False 表示休息日
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            f"https://timor.tech/api/holiday/info/{today_str}",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0:
            day_type = data["type"]["type"]
            type_name = data["type"]["name"]
            print(f"📅 今日 {today_str} 判定为: {type_name} (type={day_type})")
            # type 0=工作日, 3=调休补班 → 上班; 1=周末, 2=节假日 → 休息
            return day_type in (0, 3)
        else:
            print(f"⚠️ 节假日API返回异常: {data}，默认按工作日处理")
            return True
    except Exception as e:
        print(f"⚠️ 节假日API请求失败: {e}，默认按工作日处理")
        return True


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始获取天气...")

    # 节假日判断：休息日使用假日时段
    is_work = is_workday()
    if not is_work:
        print("🎉 今天是休息日，切换为假日时段 (10:00-22:00)")
        m_start, m_end = 10, 16  # 白天出门: 10~16点
        e_start, e_end = 17, 22  # 晚间出门: 17~22点
    else:
        m_start, m_end = MORNING_START, MORNING_END
        e_start, e_end = EVENING_START, EVENING_END

    daily_data, morning_hours, evening_hours = fetch_weather(
        morning_start=m_start,
        morning_end=m_end,
        evening_start=e_start,
        evening_end=e_end,
    )

    print(
        f"📅 {daily_data['date']} | {weathercode_desc(daily_data['weathercode'])} | "
        f"🌡️ {daily_data['temp_min']}~{daily_data['temp_max']}°C | "
        f"☔ {daily_data['precip_prob_max']}% | ☀️ UV {daily_data['uv_index_max']}"
    )

    # 分析早晚通勤时段
    all_hours = morning_hours + evening_hours
    morning_need, morning_reason = _analyze_hours(morning_hours)
    evening_need, evening_reason = _analyze_hours(evening_hours)

    # 阵风 & UV
    max_gust = max((h["wind_gust"] for h in all_hours), default=0)
    max_uv = max((h["uv_index"] for h in all_hours), default=0)
    # 也取全天UV最大值作兜底
    max_uv = max(max_uv, daily_data.get("uv_index_max", 0))

    decisions = {
        "need_umbrella": morning_need or evening_need,
        "umbrella_reason": " / ".join(
            filter(None, [morning_reason, evening_reason])
        ),
        "need_sun_umbrella": max_uv >= UV_THRESHOLD,
        "max_uv": max_uv,
        "wind_warning": max_gust >= WIND_GUST_THRESHOLD,
        "max_gust": max_gust,
    }

    # 打印摘要
    print(
        f"  🌅 早间通勤: {'⚠️ ' + morning_reason if morning_need else '✅ 无需带伞'}"
    )
    print(
        f"  🌇 晚间通勤: {'⚠️ ' + evening_reason if evening_need else '✅ 无需带伞'}"
    )
    print(
        f"  💨 最大阵风: {max_gust}km/h {'⚠️ 风大' if decisions['wind_warning'] else '✅'}"
    )
    print(
        f"  ☀️ UV最大值: {max_uv} {'⚠️ 需防晒' if decisions['need_sun_umbrella'] else '✅'}"
    )

    # 发送邮件
    if (
        decisions["need_umbrella"]
        or decisions["need_sun_umbrella"]
        or decisions["wind_warning"]
    ):
        print("📬 发送天气提醒邮件...")
        sent = send_email(
            daily_data,
            morning_hours,
            evening_hours,
            decisions,
            morning_start=m_start,
            morning_end=m_end,
            evening_start=e_start,
            evening_end=e_end,
            is_workday=is_work,
        )
        if not sent:
            print("⚠️ 天气提醒邮件未发送成功，但流程继续执行。")
    else:
        print("✅ 今日天气良好，无需提醒，不发送邮件。")


if __name__ == "__main__":
    main()
