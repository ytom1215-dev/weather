import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- 1. 設定・緯度経度辞書 ---
LOCATION_COORDS = {
    "長島": {"lat": 32.188, "lon": 130.141},
    "西之表": {"lat": 30.733, "lon": 131.000},
    "中種子": {"lat": 30.550, "lon": 130.950},
    "南種子": {"lat": 30.383, "lon": 130.866},
    "指宿": {"lat": 31.233, "lon": 130.633},
    "農業開発総合センター熊毛支場": {"lat": 30.702, "lon": 130.981}
}

file_name = "normals_daily.csv"
ALIGN_YEAR = 2024  # グラフのX軸（うるう年対応）を揃える基準年

# --- 2. データ読み込み ---
@st.cache_data
def load_normal_data():
    try:
        df = pd.read_csv(file_name, encoding="shift-jis")
    except (FileNotFoundError, UnicodeDecodeError):
        try:
            df = pd.read_csv(file_name, encoding="utf-8")
        except:
            st.error(f"⚠️ `{file_name}` が見つかりません。")
            st.stop()
            
    temp_date = pd.to_datetime(df["日付"], errors="coerce")
    df["日付"] = pd.to_datetime(f"{ALIGN_YEAR}-" + temp_date.dt.strftime('%m-%d'), errors="coerce")
    return df.dropna(subset=['日付'])

# --- 3. Open-Meteo APIから指定した年のデータを一括取得 ---
@st.cache_data(ttl="1d")
def fetch_weather_data_by_year(target_year):
    now = datetime.now()
    current_year = now.year
    
    # APIリクエストの開始日
    start_date = f"{target_year}-01-01"
    
    # 終了日の判定（今年なら5日前、過去なら年末まで）
    if target_year == current_year:
        end_date = (now - timedelta(days=5)).strftime('%Y-%m-%d')
    else:
        end_date = f"{target_year}-12-31"
    
    lats = ",".join([str(v["lat"]) for v in LOCATION_COORDS.values()])
    lons = ",".join([str(v["lon"]) for v in LOCATION_COORDS.values()])
    
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lats}&longitude={lons}&start_date={start_date}&end_date={end_date}&daily=temperature_2m_mean,precipitation_sum&timezone=Asia%2FTokyo"
    
    response = requests.get(url)
    if response.status_code != 200:
        st.error(f"⚠️ {target_year}年の気象データ取得に失敗しました。")
        return {}
        
    data = response.json()
    loc_names = list(LOCATION_COORDS.keys())
    result_dict = {}
    
    for i, loc in enumerate(loc_names):
        loc_data = data[i] if isinstance(data, list) else data
        df = pd.DataFrame({
            "フル日付": pd.to_datetime(loc_data["daily"]["time"]),
            "気温": loc_data["daily"]["temperature_2m_mean"],
            "降水量": loc_data["daily"]["precipitation_sum"]
        })
        df = df.dropna(subset=["フル日付"])
        # 平年値と比較するために、X軸の日付を基準年（2024年）に固定
        df["日付"] = pd.to_datetime(f"{ALIGN_YEAR}-" + df["フル日付"].dt.strftime('%m-%d'), errors="coerce")
        result_dict[loc] = df
        
    return result_dict

# --- 4. 画面レイアウト ---
st.set_page_config(page_title="鹿児島気象ダッシュボード", layout="wide")
st.title("🌡️ 鹿児島6地点 気温・降水量ダッシュボード")

df_normal = load_normal_data()

# サイドバー設定
current_year = datetime.now().year
st.sidebar.header("⚙️ データ設定")

# 選択肢を動的に生成（今年から過去3年分）
years_options = [current_year, current_year-1, current_year-2]
selected_year = st.sidebar.selectbox("表示・比較する年を選択", years_options, index=1)

with st.spinner(f"{selected_year}年のデータを取得しています..."):
    weather_data_dict = fetch_weather_data_by_year(selected_year)

# 表示期間の設定
st.sidebar.subheader("📅 表示期間")
s_date = st.sidebar.date_input("開始日", value=datetime(selected_year, 1, 1))
e_date = st.sidebar.date_input("終了日", value=datetime(selected_year, 12, 31))
show_precip = st.sidebar.checkbox("降水量を表示する", value=True)

# 基準年(2024)に変換してフィルタリング
start_dt = pd.to_datetime(f"{ALIGN_YEAR}-{s_date.strftime('%m-%d')}")
end_dt = pd.to_datetime(f"{ALIGN_YEAR}-{e_date.strftime('%m-%d')}")

# モード選択
mode = st.radio("分析モード", ["平年値と選択した年の比較", "2地点間の比較"])

def filter_data(loc_name, start, end):
    n_data = df_normal[(df_normal["地点"] == loc_name) & (df_normal["日付"] >= start) & (df_normal["日付"] <= end)]
    c_data = pd.DataFrame()
    if loc_name in weather_data_dict:
        c_df = weather_data_dict[loc_name]
        c_data = c_df[(c_df["日付"] >= start) & (c_df["日付"] <= end)]
    return n_data, c_data

# --- 5. グラフ描画 ---
if mode == "平年値と選択した年の比較":
    target = st.selectbox("地点を選択", list(LOCATION_COORDS.keys()))
    n_data, c_data = filter_data(target, start_dt, end_dt)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 平年気温（点線）
    fig.add_trace(go.Scatter(x=n_data["日付"], y=n_data["平年気温"], name="平年値", line=dict(dash='dot', color='gray')), secondary_y=False)
    
    if not c_data.empty:
        # 選択した年の気温
        fig.add_trace(go.Scatter(x=c_data["日付"], y=c_data["気温"], name=f"{selected_year}年の気温", line=dict(color='blue', width=2)), secondary_y=False)
        # 降水量（棒グラフ）
        if show_precip:
            fig.add_trace(go.Bar(x=c_data["日付"], y=c_data["降水量"], name=f"{selected_year}年の降水量", marker_color='rgba(0, 0, 255, 0.3)'), secondary_y=True)

    fig.update_layout(title=f"{target}の推移 ({selected_year}年)", hovermode="x unified")
    fig.update_yaxes(title_text="気温 (℃)", secondary_y=False)
    fig.update_yaxes(title_text="降水量 (mm)", secondary_y=True, showgrid=False)
    fig.update_xaxes(tickformat="%m/%d")
    st.plotly_chart(fig, use_container_width=True)

elif mode == "2地点間の比較":
    col1, col2 = st.columns(2)
    with col1: loc1 = st.selectbox("地点1", list(LOCATION_COORDS.keys()), index=1)
    with col2: loc2 = st.selectbox("地点2", list(LOCATION_COORDS.keys()), index=5)
    
    n1, c1 = filter_data(loc1, start_dt, end_dt)
    n2, c2 = filter_data(loc2, start_dt, end_dt)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 地点1
    fig.add_trace(go.Scatter(x=n1["日付"], y=n1["平年気温"], name=f"{loc1} (平年)", line=dict(dash='dot', color='royalblue')), secondary_y=False)
    if not c1.empty:
        fig.add_trace(go.Scatter(x=c1["日付"], y=c1["気温"], name=f"{loc1} ({selected_year}年)", line=dict(color='blue', width=2)), secondary_y=False)
        if show_precip:
            fig.add_trace(go.Bar(x=c1["日付"], y=c1["降水量"], name=f"{loc1} 降水", marker_color='rgba(65, 105, 225, 0.2)'), secondary_y=True)
            
    # 地点2
    fig.add_trace(go.Scatter(x=n2["日付"], y=n2["平年気温"], name=f"{loc2} (平年)", line=dict(dash='dot', color='indianred')), secondary_y=False)
    if not c2.empty:
        fig.add_trace(go.Scatter(x=c2["日付"], y=c2["気温"], name=f"{loc2} ({selected_year}年)", line=dict(color='red', width=2)), secondary_y=False)
        if show_precip:
            fig.add_trace(go.Bar(x=c2["日付"], y=c2["降水量"], name=f"{loc2} 降水", marker_color='rgba(255, 0, 0, 0.2)'), secondary_y=True)

    fig.update_layout(title=f"{loc1} vs {loc2} 比較 ({selected_year}年)", barmode='group', hovermode="x unified")
    fig.update_yaxes(title_text="気温 (℃)", secondary_y=False)
    fig.update_yaxes(title_text="降水量 (mm)", secondary_y=True, showgrid=False)
    fig.update_xaxes(tickformat="%m/%d")
    st.plotly_chart(fig, use_container_width=True)
