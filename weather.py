import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 緯度経度辞書
LOCATION_COORDS = {
    "長島": {"lat": 32.188, "lon": 130.141},
    "西之表": {"lat": 30.733, "lon": 131.000},
    "中種子": {"lat": 30.550, "lon": 130.950},
    "南種子": {"lat": 30.383, "lon": 130.866},
    "指宿": {"lat": 31.233, "lon": 130.633}
}

# 2. ローカルCSVの読み込み（変更なし）
file_name = "normals_daily.csv"

@st.cache_data
def load_normal_data():
    try:
        df = pd.read_csv(file_name, encoding="shift-jis")
    except FileNotFoundError:
        st.error(f"⚠️ エラー: `{file_name}` が見つかりません。")
        st.stop()
    except UnicodeDecodeError:
        df = pd.read_csv(file_name, encoding="utf-8")
        
    temp_date = pd.to_datetime(df["日付"], errors="coerce")
    df["日付"] = pd.to_datetime("2024-" + temp_date.dt.strftime('%m-%d'), errors="coerce")
    return df.dropna(subset=['日付'])

df_normal = load_normal_data()

# 3. Open-Meteoから「全地点の一括データ」を取得する関数
# ttl="1d" を設定し、24時間はAPIを叩かずキャッシュを利用する
@st.cache_data(ttl="1d")
def fetch_all_current_year_data():
    now = datetime.now()
    year = now.year
    end_date = (now - timedelta(days=5)).strftime('%Y-%m-%d')
    start_date = f"{year}-01-01"
    
    # 複数地点をカンマ区切りの文字列に変換
    lats = ",".join([str(v["lat"]) for v in LOCATION_COORDS.values()])
    lons = ",".join([str(v["lon"]) for v in LOCATION_COORDS.values()])
    
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lats}&longitude={lons}&start_date={start_date}&end_date={end_date}&daily=temperature_2m_mean&timezone=Asia%2FTokyo"
    
    response = requests.get(url)
    if response.status_code != 200:
        st.error("⚠️ APIからの最新データ取得に失敗しました。")
        return {}
        
    data = response.json()
    
    # 複数地点を取得した場合、dataはリスト形式で返ってくるため地点順に処理
    loc_names = list(LOCATION_COORDS.keys())
    result_dict = {}
    
    for i, loc in enumerate(loc_names):
        loc_data = data[i] # i番目の地点のデータ
        df = pd.DataFrame({
            "フル日付": pd.to_datetime(loc_data["daily"]["time"]),
            "気温": loc_data["daily"]["temperature_2m_mean"]
        })
        df = df.dropna()
        # 比較用に2024年の日付に変換
        df["日付"] = pd.to_datetime("2024-" + df["フル日付"].dt.strftime('%m-%d'), errors="coerce")
        result_dict[loc] = df
        
    return result_dict

# 4. 画面レイアウト
st.title("🌡️ 鹿児島5地点 気温比較ダッシュボード")

# バックグラウンドでAPIデータを一括取得（初回のみスピナーを表示）
with st.spinner("最新の気象データを取得しています..."):
    current_year_data_dict = fetch_all_current_year_data()

# サイドバー：表示期間の設定
st.sidebar.header("📅 表示期間の設定")
st.sidebar.write("比較したい期間を選択してください。")
s_date = st.sidebar.date_input("開始日", value=datetime(2024, 2, 1))
e_date = st.sidebar.date_input("終了日", value=datetime(2024, 5, 1))

start_dt = pd.to_datetime(f"2024-{s_date.strftime('%m-%d')}")
end_dt = pd.to_datetime(f"2024-{e_date.strftime('%m-%d')}")

# モード選択
mode = st.radio("分析モード", ["平年値と今年の比較", "2地点間の比較（平年含めて4系列）"])

# データフィルタリング用の共通関数
def filter_data(loc_name, start, end):
    n_data = df_normal[(df_normal["地点"] == loc_name) & (df_normal["日付"] >= start) & (df_normal["日付"] <= end)]
    
    c_data = pd.DataFrame()
    if loc_name in current_year_data_dict:
        c_df = current_year_data_dict[loc_name]
        c_data = c_df[(c_df["日付"] >= start) & (c_df["日付"] <= end)]
        
    return n_data, c_data

if mode == "平年値と今年の比較":
    target = st.selectbox("地点を選択", list(LOCATION_COORDS.keys()))
    normal_data, current_data = filter_data(target, start_dt, end_dt)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=normal_data["日付"], y=normal_data["平年気温"], mode='lines', name="平年値", line=dict(dash='dot', color='gray')))
    
    if not current_data.empty:
        fig.add_trace(go.Scatter(x=current_data["日付"], y=current_data["気温"], mode='lines', name="今年", line=dict(color='blue', width=2)))
    
    fig.update_layout(title=f"{target}の気温推移", xaxis_title="日付", yaxis_title="気温 (℃)", hovermode="x unified")
    fig.update_xaxes(tickformat="%m/%d", hoverformat="%m/%d")
    
    # 画面幅にフィットさせる
    st.plotly_chart(fig, use_container_width=True)

elif mode == "2地点間の比較（平年含めて4系列）":
    col1, col2 = st.columns(2)
    with col1:
        loc1 = st.selectbox("地点1", list(LOCATION_COORDS.keys()), index=1)
    with col2:
        loc2 = st.selectbox("地点2", list(LOCATION_COORDS.keys()), index=4)
    
    n1, c1 = filter_data(loc1, start_dt, end_dt)
    n2, c2 = filter_data(loc2, start_dt, end_dt)
    
    fig = go.Figure()
    # 地点1
    fig.add_trace(go.Scatter(x=n1["日付"], y=n1["平年気温"], mode='lines', name=f"{loc1} (平年)", line=dict(dash='dot', color='royalblue')))
    if not c1.empty:
        fig.add_trace(go.Scatter(x=c1["日付"], y=c1["気温"], mode='lines', name=f"{loc1} (今年)", line=dict(color='blue', width=2)))
        
    # 地点2
    fig.add_trace(go.Scatter(x=n2["日付"], y=n2["平年気温"], mode='lines', name=f"{loc2} (平年)", line=dict(dash='dot', color='indianred')))
    if not c2.empty:
        fig.add_trace(go.Scatter(x=c2["日付"], y=c2["気温"], mode='lines', name=f"{loc2} (今年)", line=dict(color='red', width=2)))
    
    fig.update_layout(title=f"{loc1} vs {loc2} 比較", xaxis_title="日付", yaxis_title="気温 (℃)", hovermode="x unified")
    fig.update_xaxes(tickformat="%m/%d", hoverformat="%m/%d")
    
    # 画面幅にフィットさせる
    st.plotly_chart(fig, use_container_width=True)