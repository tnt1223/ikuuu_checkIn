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


def fetch_weather():
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

    morning_hours = extract_hourly_range(MORNING_START, MORNING_END)
    evening_hours = extract_hourly_range(EVENING_START, EVENING_END)

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
        return f'<div style="text-align: center; padding: 20px; color: #706C64; font-size: 14px; background-color: #F8F7F5; border: 1px solid #EAE8E1; border-radius: 8px;">暂无{label}数据</div>'

    rows = ""
    for h in hours:
        precip_prob = h['precip_prob']
        uv = h['uv_index']

        precip_color = "#C35338" if precip_prob >= 50 else "#706C64"
        precip_fw = "600" if precip_prob >= 50 else "400"
        uv_color = "#B57A1E" if uv >= UV_THRESHOLD else "#706C64"
        uv_fw = "600" if uv >= UV_THRESHOLD else "400"
        gust_color = (
            "#B55A1E" if h['wind_gust'] >= WIND_GUST_THRESHOLD else "#706C64"
        )

        rows += f"""<tr>
  <td style="padding: 12px 6px; text-align: center; border-bottom: 1px solid #F0EEE9; font-weight: 500; color: #2D2A26;">{h['hour']}:00</td>
  <td style="padding: 12px 6px; text-align: center; border-bottom: 1px solid #F0EEE9; color: #4B4944;">{weathercode_desc(h['weathercode'])}<br><span style="color: #8C887F; font-size: 11px;">{h['temp']}°C</span></td>
  <td style="padding: 12px 6px; text-align: center; border-bottom: 1px solid #F0EEE9; color: {precip_color}; font-weight: {precip_fw};">{precip_prob}%<br><span style="color: #9C988F; font-size: 11px; font-weight: 400;">{h['precip']}mm</span></td>
  <td style="padding: 12px 6px; text-align: center; border-bottom: 1px solid #F0EEE9; color: {uv_color}; font-weight: {uv_fw};">{uv}</td>
  <td style="padding: 12px 6px; text-align: center; border-bottom: 1px solid #F0EEE9; color: {gust_color}; font-size: 12px;">{h['wind_gust']}<span style="font-size:10px;">km/h</span></td>
</tr>"""

    return f"""<table width="100%" border="0" cellpadding="0" cellspacing="0" style="border-collapse: collapse; font-size: 13px; background-color: #FFFFFF; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
<thead>
  <tr style="background-color: #F8F7F5;">
    <th style="padding: 10px 6px; font-weight: 600; color: #524F4A; text-align: center; border-bottom: 1px solid #EAE8E1;">时间</th>
    <th style="padding: 10px 6px; font-weight: 600; color: #524F4A; text-align: center; border-bottom: 1px solid #EAE8E1;">天气</th>
    <th style="padding: 10px 6px; font-weight: 600; color: #524F4A; text-align: center; border-bottom: 1px solid #EAE8E1;">降水</th>
    <th style="padding: 10px 6px; font-weight: 600; color: #524F4A; text-align: center; border-bottom: 1px solid #EAE8E1;">UV</th>
    <th style="padding: 10px 6px; font-weight: 600; color: #524F4A; text-align: center; border-bottom: 1px solid #EAE8E1;">阵风</th>
  </tr>
</thead>
<tbody>{rows}</tbody>
</table>"""


def send_email(daily_data, morning_hours, evening_hours, decisions):
    """通过QQ邮箱发送美化天气邮件"""
    date_str = daily_data["date"]

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

    # --- 建议模块重构 (Claude 护眼色彩系统) ---
    recs_html = ""

    # 1. 降水建议
    if has_rain:
        if has_wind:
            recs_html += f'<div style="background-color: #FCF9F7; border: 1px solid #F0DFDA; border-left: 4px solid #D47963; padding: 12px 16px; margin-bottom: 12px; border-radius: 8px; font-size: 14px;"><strong style="color: #8C4735; display: block; margin-bottom: 4px; font-weight: 600;">🧥 需防雨 (风大，雨伞易失效)</strong><span style="color: #A36453;">{decisions["umbrella_reason"]}。且阵风达 {decisions["max_gust"]}km/h，强烈建议穿防水雨衣/防风外套。</span></div>'
        else:
            recs_html += f'<div style="background-color: #FCF9F7; border: 1px solid #F0DFDA; border-left: 4px solid #D47963; padding: 12px 16px; margin-bottom: 12px; border-radius: 8px; font-size: 14px;"><strong style="color: #8C4735; display: block; margin-bottom: 4px; font-weight: 600;">☔ 需带雨伞</strong><span style="color: #A36453;">{decisions["umbrella_reason"]}</span></div>'

    # 2. 纯大风建议
    if has_wind and not has_rain:
        recs_html += f'<div style="background-color: #FDFCFA; border: 1px solid #EBE4D5; border-left: 4px solid #D5A651; padding: 12px 16px; margin-bottom: 12px; border-radius: 8px; font-size: 14px;"><strong style="color: #927438; display: block; margin-bottom: 4px; font-weight: 600;">💨 阵风较大 ({decisions["max_gust"]}km/h)</strong><span style="color: #A88741;">风力较强，出行建议穿防风外套，注意高空坠物。</span></div>'

    # 3. 防晒建议
    if has_sun:
        if has_wind:
            recs_html += f'<div style="background-color: #FDFBEE; border: 1px solid #EAE2CA; border-left: 4px solid #D5A651; padding: 12px 16px; margin-bottom: 12px; border-radius: 8px; font-size: 14px;"><strong style="color: #927438; display: block; margin-bottom: 4px; font-weight: 600;">🧴 需防晒 (建议涂防晒霜/戴帽子)</strong><span style="color: #A88741;">UV达 {decisions["max_uv"]}。由于今日阵风较大，撑遮阳伞出行不便，建议换用其他防晒方式。</span></div>'
        else:
            recs_html += f'<div style="background-color: #FDFBEE; border: 1px solid #EAE2CA; border-left: 4px solid #D5A651; padding: 12px 16px; margin-bottom: 12px; border-radius: 8px; font-size: 14px;"><strong style="color: #927438; display: block; margin-bottom: 4px; font-weight: 600;">⛱️ 需带遮阳伞 (UV {decisions["max_uv"]})</strong><span style="color: #A88741;">紫外线指数较高，出门建议携带遮阳伞或涂抹防晒霜。</span></div>'

    if not recs_html:
        recs_html = '<div style="background-color: #F6F9F6; border: 1px solid #DFEBE1; border-left: 4px solid #6D9E77; padding: 12px 16px; margin-bottom: 12px; border-radius: 8px; font-size: 14px;"><strong style="color: #4B6E55; display: block; margin-bottom: 4px; font-weight: 600;">✅ 天气怡人</strong><span style="color: #658A70;">今日天气良好，无极端天气，安心出门！</span></div>'

    # --- 核心 HTML 结构 ---
    body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<body style="margin: 0; padding: 0; background-color: #F4F3ED; font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: #2D2A26;">
  <!-- 居中主容器 -->
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 32px auto; background-color: #FFFFFF; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04); border: 1px solid #EAE8E1;">
    <!-- 头部 -->
    <tr>
      <td style="background-color: #FAF9F6; padding: 32px 24px 24px; text-align: center; border-bottom: 1px solid #EAE8E1;">
        <h1 style="margin: 0 0 8px 0; color: #2D2A26; font-size: 26px; font-weight: 500; font-family: ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif; letter-spacing: -0.3px;">🌤️ 每日天气提醒</h1>
        <p style="margin: 0; color: #706C64; font-size: 14px; font-weight: 400;">{date_str} &nbsp;|&nbsp; 🌅 日出 {daily_data['sunrise']} &nbsp;|&nbsp; 🌇 日落 {daily_data['sunset']}</p>
      </td>
    </tr>
    <!-- 内容区 -->
    <tr>
      <td style="padding: 32px 24px 24px;">
        <!-- 全天概览 -->
        <h2 style="margin: 0 0 16px 0; font-size: 16px; color: #2D2A26; font-weight: 600; border-bottom: 1px solid #EAE8E1; padding-bottom: 8px;">📊 全天概览</h2>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 28px;">
          <tr>
            <td width="48%" style="padding: 14px; background-color: #F8F7F5; border-radius: 6px; border: 1px solid #EAE8E1;">
              <span style="display: block; font-size: 12px; color: #706C64; margin-bottom: 4px;">当前天气</span>
              <span style="display: block; font-size: 16px; color: #2D2A26; font-weight: 500;">{weathercode_desc(daily_data['weathercode'])}</span>
            </td>
            <td width="4%"></td>
            <td width="48%" style="padding: 14px; background-color: #F8F7F5; border-radius: 6px; border: 1px solid #EAE8E1;">
              <span style="display: block; font-size: 12px; color: #706C64; margin-bottom: 4px;">气温区间</span>
              <span style="display: block; font-size: 16px; color: #2D2A26; font-weight: 500;">{daily_data['temp_min']}°C ~ {daily_data['temp_max']}°C</span>
            </td>
          </tr>
          <tr><td colspan="3" height="12"></td></tr>
          <tr>
            <td width="48%" style="padding: 14px; background-color: #F8F7F5; border-radius: 6px; border: 1px solid #EAE8E1;">
              <span style="display: block; font-size: 12px; color: #706C64; margin-bottom: 4px;">最高降水</span>
              <span style="display: block; font-size: 16px; font-weight: 500; color: {'#C35338' if daily_data['precip_prob_max'] >= 50 else '#2D2A26'};">{daily_data['precip_prob_max']}% <span style="font-size:12px; color:#8C887F; font-weight:400;">({daily_data['precip_sum']}mm)</span></span>
            </td>
            <td width="4%"></td>
            <td width="48%" style="padding: 14px; background-color: #F8F7F5; border-radius: 6px; border: 1px solid #EAE8E1;">
              <span style="display: block; font-size: 12px; color: #706C64; margin-bottom: 4px;">UV / 阵风峰值</span>
              <span style="display: block; font-size: 16px; color: #2D2A26; font-weight: 500;"><span style="color: {'#B57A1E' if daily_data['uv_index_max'] >= UV_THRESHOLD else 'inherit'};">{daily_data['uv_index_max']}</span> <span style="color: #D3D0C8; font-weight: 400; padding:0 4px;">|</span> {daily_data['wind_max']}<span style="font-size:12px; font-weight:400; color:#706C64;">km/h</span></span>
            </td>
          </tr>
        </table>

        <!-- 建议区 -->
        <h2 style="margin: 0 0 16px 0; font-size: 16px; color: #2D2A26; font-weight: 600; border-bottom: 1px solid #EAE8E1; padding-bottom: 8px;">💡 今日建议</h2>
        <div style="margin-bottom: 28px;">
          {recs_html}
        </div>
        
        <!-- 早间通勤 -->
        <h2 style="margin: 0 0 12px 0; font-size: 16px; color: #2D2A26; font-weight: 600; border-bottom: 1px solid #EAE8E1; padding-bottom: 8px;">🌅 早间通勤 <span style="font-size: 13px; font-weight: 400; color: #8C887F;">({MORNING_START}:00 - {MORNING_END}:00)</span></h2>
        <div style="margin-bottom: 28px; border: 1px solid #EAE8E1; border-radius: 8px; overflow: hidden;">
          {_build_hourly_table(morning_hours, '早间通勤')}
        </div>

        <!-- 晚间通勤 -->
        <h2 style="margin: 0 0 12px 0; font-size: 16px; color: #2D2A26; font-weight: 600; border-bottom: 1px solid #EAE8E1; padding-bottom: 8px;">🌇 晚间通勤 <span style="font-size: 13px; font-weight: 400; color: #8C887F;">({EVENING_START}:00 - {EVENING_END}:00)</span></h2>
        <div style="margin-bottom: 8px; border: 1px solid #EAE8E1; border-radius: 8px; overflow: hidden;">
          {_build_hourly_table(evening_hours, '晚间通勤')}
        </div>
      </td>
    </tr>
    <!-- 底部信息 -->
    <tr>
      <td style="background-color: #FAF9F6; padding: 20px; text-align: center; border-top: 1px solid #EAE8E1;">
        <p style="margin: 0; color: #9C988F; font-size: 12px; line-height: 1.6;">本邮件由系统自动生成 &nbsp;|&nbsp; 坐标: {LAT}, {LON}</p>
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
    with smtplib.SMTP_SSL("smtp.qq.com", 465, context=context) as server:
        server.login(QQ_EMAIL, QQ_AUTH_CODE)
        server.sendmail(QQ_EMAIL, RECEIVER_EMAILS, msg.as_string())

    print(f"✅ 邮件已发送至 {', '.join(RECEIVER_EMAILS)}")


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

    # 节假日判断：休息日跳过
    if not is_workday():
        print("🎉 今天是休息日，无需通勤提醒，跳过发送。")
        return

    daily_data, morning_hours, evening_hours = fetch_weather()

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
        send_email(daily_data, morning_hours, evening_hours, decisions)
    else:
        print("✅ 今日天气良好，无需提醒，不发送邮件。")


if __name__ == "__main__":
    main()
